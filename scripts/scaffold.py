#!/usr/bin/env python3
"""
scaffold.py — regenerate the project_keel skeleton.

This is the generator for the generic project template. It is *idempotent for
structure*: it (re)writes README.md / CLAUDE.md / convention docs and the
exemplar code files, and creates empty dirs with `.keep`. It will NOT clobber
files you have authored that are not part of the skeleton.

Run:  python3 scripts/scaffold.py [TARGET_DIR]
Default TARGET_DIR is the repo root (parent of scripts/).
"""
from __future__ import annotations
import datetime
import os
import re
import sys
import textwrap

BASE = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))

# Corpus core: stamped onto every generated markdown doc so the company "one
# brain" can ingest, dedup, age-out, and govern each file. Placeholders — real
# projects set real owners/dates; `updated` is ideally derived from git.
TODAY = datetime.date.today().isoformat()


def _slug_id(relpath: str) -> str:
    """Stable, path-derived id. Keep it stable by hand when you move a file."""
    base = relpath[:-3] if relpath.endswith(".md") else relpath
    return re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower() or "doc"


def _inject_corpus_fields(relpath: str, content: str) -> str:
    """Add missing corpus core keys to a markdown frontmatter block (idempotent)."""
    if not relpath.endswith(".md") or not content.startswith("---"):
        return content  # never touch code, JSON, or Astro (.astro) frontmatter
    lines = content.split("\n")
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        return content
    present = {ln.split(":", 1)[0].strip()
               for ln in lines[1:close] if ":" in ln and not ln.startswith(" ")}
    defaults = [("id", _slug_id(relpath)), ("created", TODAY), ("updated", TODAY),
                ("visibility", "internal"), ("canonical", "true")]
    inject = [f"{k}: {v}" for k, v in defaults if k not in present]
    if not inject:
        return content
    return "\n".join(lines[:close] + inject + lines[close:])


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def w(relpath: str, content: str) -> None:
    path = os.path.join(BASE, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = _inject_corpus_fields(relpath, content.lstrip("\n"))
    with open(path, "w") as fh:
        fh.write(content)
    print("  +", relpath)


def keep(reldir: str) -> None:
    path = os.path.join(BASE, reldir, ".keep")
    os.makedirs(os.path.join(BASE, reldir), exist_ok=True)
    if not os.path.exists(path):
        open(path, "w").close()
    print("  +", os.path.join(reldir, ".keep"))


def fm(**kw) -> str:
    """Render a YAML frontmatter block from kwargs (order preserved)."""
    lines = ["---"]
    for k, v in kw.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def readme(relpath, *, title, kind, layer, summary, public_api="none",
           status="template", tags=None, body=""):
    block = fm(title=title, kind=kind, layer=layer, status=status,
               owner="TBD", public_api=public_api, tags=tags or [],
               summary=summary)
    w(os.path.join(relpath, "README.md"),
      block + f"\n# {title}\n\n{summary}\n\n" + textwrap.dedent(body).strip() + "\n")


def symlink_claude(reldir):
    """Point CLAUDE.md at the canonical AGENT.md sibling (vendor-neutral name)."""
    path = os.path.join(BASE, reldir, "CLAUDE.md")
    if os.path.islink(path):
        if os.readlink(path) == "AGENT.md":
            return
        os.remove(path)
    elif os.path.exists(path):
        os.remove(path)
    os.symlink("AGENT.md", path)
    print("  +", os.path.join(reldir, "CLAUDE.md"), "-> AGENT.md")


def claude(relpath, *, title, rules, layer="n/a", kind="rules"):
    block = fm(title=f"{title} — agent rules", kind=kind, layer=layer,
               status="template", owner="TBD",
               summary=f"Local agent rules inside {relpath or '.'}/.")
    body = "\n".join(f"- {r}" for r in rules)
    # AGENT.md is canonical; CLAUDE.md is a symlink to it so every agent tool
    # reads the same rules (see CONVENTIONS §5).
    w(os.path.join(relpath, "AGENT.md"),
      block + f"\n# Agent rules — `{relpath or '.'}/`\n\n"
      "These rules are **local and authoritative** for this directory. They "
      "inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they "
      "conflict, the more specific (this) file wins.\n\n"
      "## Rules\n\n" + body + "\n")
    symlink_claude(relpath)


# --------------------------------------------------------------------------- #
# root files
# --------------------------------------------------------------------------- #
def root_files():
    w("README.md", fm(
        title="Project Keel", kind="readme", layer="n/a",
        status="template", owner="TBD", tags=["template", "scaffold", "project_keel"],
        summary="A generic, polyglot-aware, agent-friendly project skeleton that stays honest.") + textwrap.dedent("""
        # Project Keel

        Project Keel is a generic project skeleton with a strict, documented structure that is
        friendly to both humans and coding agents (Claude Code). Every directory
        carries a `README.md` (what + frontmatter labels) and a `CLAUDE.md`
        (local rules). The single source of truth for the labeling scheme and
        the directory taxonomy is **[`CONVENTIONS.md`](CONVENTIONS.md)** — read
        it first.

        ## Top-level layout

        ```
        .
        ├── src/            # all production source
        │   ├── frontend/   #   UI / client (TS/JS-leaning)
        │   ├── backend/    #   server / domain / services (Python-leaning)
        │   ├── shared/     #   FE<->BE data contract (DTOs/enums/error codes)
        │   └── app/        #   OPTIONAL composition root (single-process apps only)
        ├── tests/          # unit (mirrors src/) + integration/e2e/smoke (by scenario)
        ├── test-docs/      # test plans, coverage register, test strategy
        ├── docs/           # architecture / specs / design / guides / reference / adr
        ├── agents/         # autonomous/LLM agents
        ├── mcp/            # Model Context Protocol servers (tool gateways)
        ├── api/            # transports: REST/OpenAPI (FastAPI), gRPC, nginx edge
        ├── wiki/           # (optional) browsable knowledge/index site
        ├── scripts/        # dev + CI automation (incl. this scaffold.py)
        ├── config/         # configuration (committed defaults + examples)
        ├── demo/           # runnable demos / examples
        ├── containers/     # Dockerfiles, compose, image build context
        ├── evals/          # eval suites (esp. for agents/models)
        ├── ops/            # deploy, IaC, runbooks, observability
        ├── models/         # model backends the agents/app run on (adapters + registry)
        ├── pyproject.toml  # Python src-layout packaging + tool config
        ├── Makefile        # task runner (test, lint, fmt, run, ...)
        └── CONVENTIONS.md  # frontmatter schema + taxonomy (READ FIRST)
        ```

        ## The three load-bearing conventions

        1. **`__init__.py` is the API.** Nothing leaves a package except through
           its `__init__.py` (`__all__`). Private modules are `_underscore`d.
           (TS analog: an `index.ts` barrel; Rust: `pub` in `mod.rs`.)
        2. **Every dir is labeled.** `README.md` + `CLAUDE.md` with YAML
           frontmatter (`kind`, `layer`, `status`, `public_api`, `tags`) so
           files sort and route mechanically.
        3. **Tests mirror only where it helps.** `tests/unit/` mirrors `src/`
           1:1; integration/e2e/smoke are organized by scenario.

        ## Getting started

        ```bash
        make help          # list tasks
        make scaffold      # (re)generate the skeleton from scripts/scaffold.py
        ```

        Delete the dirs you don't need (`wiki/`, `models/`, `evals/`,
        `containers/` are all optional) and rename `src/backend/example_feature/`
        to your first real package.

        ## Showcase demo (synced docs site)

        A minimalist docs/wiki site presents this template as a product and
        renders **live from the backend** — overview, features, the
        deterministic-check catalogue, and a browsable index of every
        doc/module/script:

        ```bash
        make site-data   # build the wiki corpus the site reads
        make run-api     # FastAPI on :8000  (project interpreter / venv)
        make run-web     # Astro on :4321, pointed at the API
        ```

        See [`docs/guides/showcase-site.md`](docs/guides/showcase-site.md).
        """).strip() + "\n")

    w("CONVENTIONS.md", fm(
        title="Conventions", kind="doc", layer="n/a", status="template",
        owner="TBD", tags=["conventions", "frontmatter", "taxonomy"],
        summary="Single source of truth for labeling (frontmatter) and the directory taxonomy.") + textwrap.dedent("""
        # Conventions

        This file defines **how files are labeled** and **what each directory
        means**. It is the contract that `README.md`/`CLAUDE.md` files and coding
        agents follow. If you change the scheme, change it here first.

        ## 1. Frontmatter (labeling for sort/route)

        Every Markdown doc (`README.md`, `CLAUDE.md`, design docs, specs) starts
        with a YAML frontmatter block. This is what lets tools, agents, and
        humans sort and route files without reading the body.

        ```yaml
        ---
        # --- human core (for humans sorting/routing files) ---
        title: Backend                       # human title
        kind: package                        # see KINDS below
        layer: backend                       # see LAYERS below
        status: stable                       # draft|stable|deprecated|template (ADRs: proposed|accepted|superseded)
        owner: team-or-person
        public_api: src/backend/__init__.py  # the boundary file, or "none"
        tags: [server, domain]
        summary: One-line purpose, <=120 chars.
        # --- corpus core (for the company "one brain": ingest/dedup/age/govern) ---
        id: backend                          # stable, unique; keep it when you move the file
        created: 2026-06-14
        updated: 2026-06-14                  # ideally derived from git, not hand-kept
        visibility: internal                 # public | internal | confidential | restricted
        canonical: true                      # true = authoritative; or a path/id to the source of truth
        ---
        ```

        **KINDS:** `readme` `rules` `package` `module` `tests` `test-doc` `doc`
        `spec` `design` `adr` `config` `script` `agent` `mcp` `api` `wiki`
        `demo` `model` `eval` `container` `ops` `tool`.

        **LAYERS:** `frontend` `backend` `shared` `app` `cross-cutting` `n/a`.

        ### Corpus core fields (the "one brain" reads these)
        These exist so a single company-wide retrieval/agent layer can ingest
        every doc without producing garbage. Each one fixes a real corpus
        failure mode:

        | Field | Values | Why the brain needs it |
        |-------|--------|------------------------|
        | `id` | stable slug, unique | cite/track a doc across renames & moves (path is not stable) |
        | `created` / `updated` | ISO dates | rank by recency; flag stale content (`updated` best derived from git) |
        | `visibility` | `public`/`internal`/`confidential`/`restricted` | never surface a confidential doc to the wrong audience |
        | `canonical` | `true` or a path/id | dedup: when the same fact lives in N places, point mirrors at the one source of truth |

        Related (set when applicable, not required): `superseded_by` — **required
        when `status: deprecated`** so the brain follows the chain to the live
        version. The scaffold stamps `id`/dates/`visibility`/`canonical` with
        safe defaults; **replace placeholder dates/owners**, and tighten
        `visibility` on anything sensitive.

        ### Code files
        Source files can't carry YAML, so the **module docstring** is the
        label, and `__all__` is the machine-checkable public API:

        ```python
        \"\"\"
        title: Example feature
        layer: backend
        public_api: yes        # this module is re-exported from the package __init__
        summary: Does the one thing this feature does.
        \"\"\"
        __all__ = ["do_thing", "Thing"]
        ```

        ## 2. Directory taxonomy

        | Dir | kind | What goes in | What does NOT |
        |-----|------|--------------|---------------|
        | `src/frontend` | package | UI, client, view logic | server/domain logic |
        | `src/backend`  | package | services, domain, persistence | UI rendering |
        | `src/shared`   | package | contracts/types used by BOTH FE+BE | anything FE- or BE-only |
        | `src/app`      | package | entrypoints, DI/wiring, CLI/`__main__` | business logic |
        | `tests/unit`   | tests | fast, isolated; **mirrors `src/`** | network/disk/process |
        | `tests/integration` | tests | 2+ real components, by scenario | full-stack journeys |
        | `tests/e2e`    | tests | full system, user journeys | unit-level asserts |
        | `tests/smoke`  | tests | "is it alive" post-deploy checks | exhaustive cases |
        | `test-docs`    | test-doc | test plans, coverage register, strategy | the tests themselves |
        | `docs`         | doc | architecture, specs, design, guides, ADRs | API code |
        | `agents`       | agent | autonomous/LLM agent brains | the MCP/API transport |
        | `mcp`          | mcp | MCP servers exposing tools | business logic (call into `src/`) |
        | `api`          | api | HTTP handlers + OpenAPI specs | business logic (call into `src/`) |
        | `wiki`         | wiki | browsable index/knowledge site (optional) | source of truth |
        | `scripts`      | script | dev/CI automation, one-shots | importable library code |
        | `config`       | config | committed defaults + `*.example.*` | secrets |
        | `demo`         | demo | runnable examples | tests |
        | `containers`   | container | Dockerfiles, compose, build context | app code |
        | `evals`        | eval | eval datasets + harness for agents/models | unit tests |
        | `ops`          | ops | deploy, IaC, runbooks, dashboards | app code |
        | `models`       | model | model backends the app/agents run on (adapters + registry, e.g. Claude Code headless) | domain logic (that's `src/`) |
        | `runtimes`     | package | agent control-flow engines: a neutral `Plan` + `Runtime` (adapters + registry, e.g. LangGraph) | domain/business logic (that's `src/`) |
        | `agents/tools` | tool | shared, thin `*.tool.md` tool-use specs (markdown adapters over `scripts/`) | tool logic (stays in `scripts/`) |

        Note: `agents/<name>/` holds **all** files for one agent — its
        `prompt.md` (system prompt), code (`__init__.py` + private `_brain.py`),
        `tools.md` (toolset manifest), and labels. Shared tools live one level
        up in `agents/tools/` (see §10).

        ## 3. The `__init__.py` boundary rule (the important one)

        A package's `__init__.py` **is its public API**. Callers import from the
        package, never from a submodule:

        ```python
        from myproj.backend import do_thing        # ✅ through the boundary
        from myproj.backend._impl import do_thing  # ❌ reaching inside
        ```

        - `__init__.py` lists `__all__` and re-exports only the public symbols.
        - Implementation modules are prefixed `_` (e.g. `_impl.py`, `_service.py`).
        - Cross-package contracts are **ABCs / `typing.Protocol`** in
          `contracts.py`, re-exported from `__init__.py`. Depend on the
          contract, not the concrete class.
        - **Polyglot analogs:** TS → a single `index.ts` barrel; Go → package
          exports (capitalized identifiers); Rust → `pub` in `mod.rs`; Java →
          package-private by default + a public façade.

        ## 4. `shared/` vs `util/`

        - **`shared/`** — domain-meaningful things shared across a section
          (types, models, contracts, constants).
        - **`util/`** — generic, domain-agnostic helpers (string, fs, time,
          retry). If a helper "knows" about your domain, it belongs in `shared/`.
        - Don't pre-create either in a tiny package. One of each per section,
          max. `util/` is not a junk drawer — review it like any other module.

        ## 5. Hidden (dot) files & directories

        Split them into **committed config** (part of the project) vs
        **generated/local** (gitignored). Scaffold the first kind, never the
        second.

        | Dot path | Commit? | Purpose |
        |----------|---------|---------|
        | `.gitignore` `.editorconfig` `.gitattributes` | ✅ | repo hygiene |
        | `.github/workflows/` or `.gitlab-ci.yml` | ✅ | CI definitions |
        | `.claude/` (`settings.json`, `skills/`, `commands/`) | ✅ | agent config shared with the team |
        | `.env.example` | ✅ | documents required env vars (no real values) |
        | `.vscode/` `.idea/` | ⚠️ optional | editor config — commit only a minimal shared subset |
        | `.env` `.env.local` | ❌ | real secrets — gitignored |
        | `.venv/` `.pytest_cache/` `.mypy_cache/` `.ruff_cache/` | ❌ | tool caches/venvs — generated, gitignored |

        Rule: a dot-dir that holds **decisions** (CI, agent rules, editor norms)
        is committed and may carry a `README.md`; a dot-dir that holds
        **generated state or secrets** is gitignored and never scaffolded.

        ### Agent-rules file: `AGENT.md` is canonical, `CLAUDE.md` is a symlink

        The per-directory agent-rules file is **`AGENT.md`** (the vendor-neutral
        name). `CLAUDE.md` is a symlink to the sibling `AGENT.md` so Claude Code
        and any other agent tool read the same rules. Edit `AGENT.md`; never edit
        the symlink. The checker requires a readable `CLAUDE.md` — the symlink
        satisfies it — so this is backward-compatible.

        ## 6. Enforcement (this is checked, not just documented)

        `scripts/check_structure.py` (run via `make check`, in CI, and as a
        pre-commit hook) fails the build if the conventions above drift:

        | Rule | What it verifies |
        |------|------------------|
        | Frontmatter | every `README.md`/`CLAUDE.md` (+ `docs/**`, `test-docs/**` md) has the required keys with valid `kind`/`layer`/`status`/`visibility` |
        | Corpus id | every `id` is unique across the corpus |
        | Corpus canonical | a path-like `canonical` pointer resolves to a real file |
        | Corpus lifecycle | `status: deprecated` requires `superseded_by` |
        | Documented dirs (§2) | every taxonomy directory that exists has both `README.md` and `CLAUDE.md` |
        | Package boundary (§3) | every `src/` dir with `.py` has an `__init__.py` that defines `__all__` |
        | `__init__` is the API (§3) | no absolute import of another package's `_private` module |
        | Authored coverage (warn) | every `__all__`-exported symbol defined in-file has a one-line docstring |
        | Tool specs governed (error) | `agents/**/*.tool.md` carry valid `kind: tool` frontmatter + a resolvable `public_api` + a valid `tool_effect` |
        | Accountability (warn) | tool/agent docs name a real `owner` (not missing or `TBD`) |
        | Tool/agent binding (error) | each agent `tools.md` ↔ each spec's `## Used by` agree (both ways); `tool_command` invokes `public_api` |
        | Project facts (§15) | `config/project.json` agrees with the tree: declared `path`/`stack`/`enabled` transport dirs exist, `enabled` ⊆ `available`, `backend.python` matches `pyproject`; an **undeclared** leftover stack/transport dir warns |
        | Agent-rules symlink (§5) | every `CLAUDE.md` is a symlink to its sibling `AGENT.md`; every `AGENT.md` has that sibling |

        Missing `owner` is a warning, not a failure. If you change the scheme
        (KINDS / LAYERS / STATUSES / VISIBILITIES) or a check, update **both**
        this file AND `scripts/check_structure.py`, then run `python3
        scripts/check_scaffold_sync.py --write` to resync the embedded copy in
        `scripts/scaffold.py` (the `scaffold-sync` check enforces that the live
        checker and the embed stay byte-identical).

        `check_structure.py` is the structural gate, but it is not the only
        deterministic check. The **full suite** — scaffold-embed sync
        (`check_scaffold_sync.py`), corpus integrity + reproducibility
        (`scripts/jobs/check_corpus.py`), and OpenAPI / AAD contract drift — is
        catalogued in **[`docs/guides/deterministic-checks.md`](docs/guides/deterministic-checks.md)**
        (each check's purpose, when to run it, and how to wire it as a hook).

        ## 7. Triggers vs doers (hooks & scheduled jobs)

        Automation has two halves; keep them in different places. A **trigger**
        says *when* to run (an event, or a clock); a **doer** is *what* runs.
        This mirrors the transport rule (`api/`/`mcp/` stay thin over `src/`).

        | Half | Lives in | Holds |
        |------|----------|-------|
        | Doer — deterministic | `scripts/hooks/` (event), `scripts/jobs/` (time) | the actual stdlib logic; `--help`, idempotent |
        | Doer — needs an LLM | `agents/` (brain) + a thin entrypoint in `scripts/` | reasoning/prompt; model comes from `models/` |
        | Trigger — event | the ecosystem's own adapter (`.pre-commit-config.yaml`, `.github/workflows/`, `.claude/settings.json`, …) | "on event → call the doer" |
        | Trigger — schedule | `ops/scheduled/` (cron/systemd/CI/cloud) | the cadence ("trigger in 2 days") |

        Rules:
        - **A trigger is a thin, vendor-specific adapter.** It records
          *when/what event* and points at a doer. It contains no logic.
        - **The doer is vendor-agnostic.** Swapping cron→systemd, or one agent
          ecosystem for another, must not touch `scripts/` or `agents/`.
        - **Keep the adapter set vendor-neutral.** Adding a second scheduler or
          hook ecosystem is a new thin adapter, never a fork of the doer.
        - LLM doers stay thin: the `scripts/` entrypoint calls into `agents/`,
          which gets its model from `models/` — no provider names in the doer.

        ## 8. Configuration: where tunable values live

        Configuration is **data the app reads**, never logic. Collate it by
        *lifecycle + consumer* so each knob has exactly one home and is easy to
        tune:

        | Kind of value | Example | Home |
        |---------------|---------|------|
        | runtime, app-wide, language-neutral | RAG chunk size, top-k, max context, ports, timeouts | `config/` — committed `default.*` / `*.example.*`, grouped by concern (e.g. `config/rag.toml`) |
        | model-backend selection / launch | which embedding model or reranker adapter + flags | `models/config/` — next to the registry that picks by name |
        | build-time, component-coupled | frontend font, colours, footer (design tokens) | with the frontend package (`src/frontend/<app>/src/styles` / theme) — the build is the consumer |
        | secret | API keys, tokens | the environment / `.env` (gitignored) — **never** `config/` |

        Decision rule: *runtime + app-wide + neutral → `config/`; provider
        launch → `models/config/`; build-time + package-coupled → with the
        package; secret → env.* Keep one source of truth: if a container or the
        `app/` layer needs a port, it reads the value from `config/` rather than
        re-declaring it. Running code receives values via injection (the `app/`
        layer loads config and passes it down) — domain code never reads files
        itself.

        ## 9. Integrating a third-party tool (e.g. cdmon)

        External tools (a code-doc monitor, a doc generator, a scanner) follow
        the same thin-adapter rule as triggers (§7): **don't vendor the tool,
        don't embed its logic.** Instead —
        - **tool**: an external dependency, installed, not copied in;
        - **config**: under `config/<tool>/` (committed defaults / examples);
        - **adapter (doer)**: a thin wrapper in `scripts/` that only invokes it
          (no tool logic), e.g. `scripts/cdmon_sync.py`;
        - **trigger**: a pre-commit/CI line (event) or `ops/scheduled/` (time);
        - **output**: generated artifacts gitignored (e.g. `.cdmon/`).

        **cdmon** is the worked example. This scheme is designed to **coexist**
        with cdmon (the code-doc drift monitor) without either tool overwriting
        the other.

        | Concern | This template owns | cdmon owns |
        |---------|--------------------|------------|
        | Frontmatter keys | top-level keys (`title`, `kind`, `id`, `visibility`, …) | the `cdm:` mapping block (`schema_version`, `fingerprint`, `region_*`, its `audience`) |
        | Doc body | prose you write | content inside `<!-- CDM:BEGIN x -->`…`<!-- CDM:END x -->` regions |
        | Config | nothing | `config/cdmon/` (lives in our `config/` dir) + `cdmon.yaml` |
        | Generated output | `wiki/` index | `.cdmon/` (gitignored) and `*.html` doc twins |

        Why it's safe:
        - cdmon **preserves foreign top-level frontmatter keys** and writes only
          under `cdm:`. Our keys survive its `heal`/`lint --fix`.
        - cdmon **discovers docs by explicit registration**, not by scanning
          frontmatter — so it ignores our `README.md`/`CLAUDE.md` unless you
          register them in its config. No accidental management.
        - Our validator **ignores nested frontmatter keys**, so the `cdm:` block
          never collides with our top-level keys.

        Rules when both tools are in play:
        - **Keep `id` in sync.** A doc's frontmatter `id` should equal the `id`
          it is registered under in cdmon's `documents:`. One identifier, two
          tools.
        - **Do not hand-edit anything under `cdm:`** or inside `CDM:BEGIN/END`
          regions — those are machine-managed.
        - **Reserve `cdm:` and `audience`** (in the cdmon sense: `user-guide` /
          `eng-guide`) for cdmon; don't repurpose them at top level.
        - Pick one HTML source of truth: cdmon's `html: true` twins **or**
          `wiki/`, not both for the same docs.

        ## 10. Agent tools (`agents/tools/`) & toolset manifests

        An agent's reasoning lives in its own dir; the **tools** it can use are
        shared. A `kind: tool` spec (`agents/tools/<name>.tool.md`) is a **thin
        adapter** that tells any LLM agent how to invoke a `scripts/` doer — the
        tool's logic stays in the script (cross-ref §7/§9). Frontmatter:
        `public_api` (the wrapped script, validated to exist), `tool_command`
        (the exact argv), `tool_effect` (`read-only` | `writes` | `model-call`),
        and a real `owner`. Body sections: Command, Purpose, When to use, Args,
        Output, Side effects (begins with `READ-ONLY`/`WRITES`), Used by.

        Each agent declares the tools it may invoke in `agents/<name>/tools.md`
        (a one-table manifest). The binding is **bidirectional**: a tool's
        `## Used by` lists the agents, and each agent's manifest rows point back
        at the specs. An agent's reasoning prose lives only in its `prompt.md`
        (a vendor-neutral system prompt, no frontmatter).

        ## 11. The wiki corpus (the one-brain index)

        The repo is the *structured source* for a company wiki: source →
        summarize → split into sections → summarize → link by entity/keyword
        into a tree an agent traverses to answer. `scripts/jobs/build_corpus.py`
        walks the repo into `wiki/corpus.json` — a flat list of **nodes**
        (`doc` | `module` | `section` | `symbol`) with tree edges
        (`parent`/`children`), `tags`, and authored summaries;
        `scripts/jobs/link_corpus.py` adds entity/keyword **link edges**.

        - **Provenance.** `summary_source` is `authored` | `generated`. For a
          repo source the authored docstring/frontmatter IS the canonical
          summary — extract it, never regenerate it. Generation is a **fallback
          for gaps only** (nodes with no authored summary), always marked
          `generated`, and never overwrites authored text. Link edges carry
          `source` (`deterministic` | `generated`) for the same reason.
        - **Deterministic vs LLM.** `build_corpus`/`link_corpus`/`query_corpus`
          are pure stdlib and model-free (reproducible in CI/cron). Summary
          gap-fill is the `index_enforcer`'s LLM job (dry-run by default); rich
          `semantic` links (`source: generated`) are a planned extension it may
          add later. Answer synthesis is the `wiki_navigator`'s LLM job.
        - `wiki/corpus.json` is **generated and gitignored** — a view over the
          repo, never a source of truth (like the rest of `wiki/`).

        ## 12. Accountability & ownership granularity

        Every corpus node resolves to an `owner`, carried by one of three
        markers (one token, `owner:`, grammar `[A-Za-z0-9._@-]+`):
        - **doc/module** — frontmatter `owner` (a module inherits its nearest
          package `README.md` owner);
        - **section** — an HTML comment under the heading: `<!-- owner: x -->`;
        - **symbol** — an `owner: x` line in the docstring.

        Resolution is **finest-wins, then inherit**: a marker beats frontmatter
        beats the parent's resolved owner; `owner_source` records which
        (`marker` | `frontmatter` | `inherited` | `none`). The `TBD` placeholder
        counts as unowned. Corpus nodes that resolve to `owner_source: none` are
        reported by `scripts/accountability_report.py`. Independently, at commit
        time `check_F` warns when a `kind: tool`/`agent` frontmatter doc has a
        missing/`TBD` owner (it inspects frontmatter only, not corpus nodes).

        ## 13. Authoring a new agent

        A new `agents/<name>/` is done when it has: `__init__.py` (defines
        `__all__`, re-exports the public entrypoint), a private `_brain.py`
        (policy/prompt; gets its model from `models.get_model`, never a
        provider), a markdown `prompt.md` (system prompt), a `tools.md`
        manifest, and `README.md` + `AGENT.md` (+ `CLAUDE.md` symlink). Default
        any model call / state change to **dry-run** (`execute=False`). The
        `index_enforcer`/`wiki_navigator` examples return frozen dataclasses
        (not a bare `str` like `triage`) because retrieval needs structured
        citations + provenance — a deliberate, documented exception.

        An agent here is an **in-process** brain (the host imports it; it gets its
        model from `models/`). A service that crosses a **process boundary** to be
        reached as an agent does not belong in `agents/` — it publishes an **agent
        surface** (§14) instead.

        ## 14. Exposing a service as an agent (the agent surface)

        A service that crosses a process boundary can be made discoverable as an
        agent. Like every integration here, the **neutral concept comes first and the
        vendor wiring is a thin adapter** (mirrors `models/` hiding a provider, §7
        triggers hiding cron-vs-systemd, §9 third-party tools).

        - **Neutral concept — the *agent surface*.** A service self-describes
          (`card`), answers (`ask`), and reports liveness (`health`). That contract is
          the `AgentSurface` protocol + neutral `AgentCard`/`AgentReply` in
          `src/backend/agent_surface/`. It carries no wire format, version envelope, or
          well-known path. **This is the standard**, and the root rules point at it.
        - **Dialect — a thin adapter.** A wire format that serializes a surface is one
          interchangeable option. The shipped reference is **AAD** (Aion Agent
          Discovery) in `api/rest_fastapi/aad/`: it renders any `AgentSurface` to a
          descriptor (`/.well-known/aion-agent.json` + fallback), `ask`/`health`, and
          FastAPI's free `/openapi.json`. A second dialect (A2A, MCP-native, a plugin
          manifest) is a **sibling adapter over the same surface** — never an edit to
          the contract. The vendor name appears only inside the adapter, never in the
          contract or the root rules.
        - **The opt-in rule.** Cross a process boundary ⇒ publish an agent surface
          (AAD is the default dialect). Compiled in-process ⇒ stay `function` (no
          port, no descriptor; §13). Do not add a network boundary just to be uniform.
        - **Serve, don't discover.** A template service only **serves** its own
          descriptor. The consumer side (fetching arbitrary descriptor URLs, the SSRF/
          trusted-host allowlist, version normalization) is the platform's concern and
          is deliberately not vendored here.
        - **Generated schema, versioned.** `config/agent_surface/aad-v1.0.schema.json`
          is **generated** from the `AadDescriptor` model
          (`make agent-surface-schema`), so the published wire contract can't drift
          from the code; `tests/integration/test_aad_conformance.py` is the CI gate.
          `aad_version` is `MAJOR.MINOR` — minor is additive-only, major is breaking, a
          shipped field is never mutated. `auth.kind` declares *that* auth is needed,
          never the secret; `none` is dev-only.

        See `docs/guides/agent-surface.md` (how-to) and `docs/adr/0002-agent-surface-and-discovery.md` (the decision).

        ## 15. Project facts manifest (`config/project.json`)

        The repo is **polyglot by design** (Python backend, a TypeScript frontend,
        protobuf + nginx at the edges), so "what is this project made of" is not a
        single language — it is a set of **per-layer facts**. Those facts live in one
        machine-readable manifest, `config/project.json`, enforced by
        `check_structure.py` (`check_H`) so they cannot silently drift from the tree.

        It is keyed **by layer/concern, never one global `language`**:

        - `layers.<layer>` — per layer: a `language`, plus a `path` (backend) or a
          `root` + `available` stack list (frontend) and the chosen `stack` (`null`
          while the template still ships more than one — pick one, delete the rest).
        - `transports` — `enabled` ⊆ `available`, a name→dir map of the shipped
          transports (REST / gRPC / nginx-edge / MCP).

        `check_H` **errors** on a hard contradiction (a declared `path`/`stack`/
        `enabled` transport dir that is missing; `enabled` not in `available`; a
        `backend.python` that disagrees with `pyproject.toml`'s `requires-python`) and
        **warns** on an *undeclared leftover* — a stack dir under the frontend `root`,
        or a transport dir under `api/`, that the manifest doesn't list. So a stack you
        forgot to record (or meant to delete) is surfaced, not blocked.

        Why JSON here, and why this and not prose: a manifest is read by **code** (a
        deterministic gate), whereas `AGENT.md` prose is read by a **model**
        (advisory) — they're complementary, not rivals. JSON specifically because the
        checker must run under the host's old `python3` in pre-commit, where `tomllib`
        (3.11+) is absent; stdlib `json` parses everywhere. TOML stays right for
        runtime tunables (§8). `config/project.json` is a committed **decision** (like
        the generated agent-surface schema, §14) — read by the checker, not the app.

        ## 16. Agent control flow (`runtimes/`): a neutral Plan, engines are adapters

        An agent's reasoning is a *policy*; the order its steps run in is *control
        flow*. Keep control flow a **neutral concept** and make the execution engine
        one interchangeable adapter — the same rule as `models/` (providers), triggers
        (§7), and the agent surface (§14). LangGraph being open-source does **not**
        exempt it from this (§9): the coupling the rule bans lives at the import/API
        boundary, not the licence.

        - **Neutral concept — the `Plan`.** An agent declares its flow as a `Plan`: a
          flowchart of typed `Step`s and `Edge`s, defined in `runtimes/` alongside the
          `Runtime` ABC. A `Step` carries an `effect` from the §10 `tool_effect`
          vocabulary (`read-only` | `writes` | `model-call`); an `Edge` may carry a pure
          `when(state)` predicate. This makes branching **inspectable data**, not nested
          `if`s, and puts the **dry-run effect-guard in one place**: a `writes` or
          `model-call` step is skipped unless the run is authorized with `execute=True`.
        - **Default engine — stdlib, reproducible.** The default `Runtime` is the
          pure-stdlib `inprocess` walker; it is the *reference semantics* and is what
          CI, pre-commit, and the app always get — no dependency, no install.
        - **Vendor engine — one adapter, lazily loaded.** A graph engine such as
          **LangGraph** is *one* `Runtime` adapter (`runtimes/langgraph_adapter.py`),
          selected by name (`get_runtime("langgraph")`) and registered **lazily** so the
          default path imports nothing extra. Its dependency is an **optional extra** in
          `pyproject.toml`, never in `dependencies`. The vendor name appears only inside
          that adapter and its registry thunk — never in `contracts.py`, the default
          engine, or any `agents/` brain.
        - **Adapters change execution, never semantics.** Every engine produces the same
          final state and honours the same dry-run guard and edge order as the
          `inprocess` reference — machine-checked by
          `tests/unit/runtimes/test_runtime_equivalence.py` (skipped when the optional
          engine isn't installed).
        - **The opt-in rule.** Default to `inprocess`. Adopt a heavier engine **per
          agent** only when a real trigger arrives — durable resume across a crash, a
          mid-flow human approval, or a genuine cycle/fan-out — not for uniformity.
        - **Manifest.** `config/project.json` carries an optional `runtimes` block
          (`default` + `available`), validated by `check_structure.py` (`check_H`).

        ## 17. Development loops (how to work in this repo)

        Code here is produced by **bounded, gated loops**, not one-shot edits — and
        any agent working in the repo follows them by default (the imperative form
        is in the root `AGENT.md`). These govern *how you work*; their executable
        analog — a loop a program runs unattended — is a `Plan` on a `Runtime` (§16,
        `runtimes/`), the same shape expressed as data.

        - **Slice work vertically.** The tree is layered (`app → {frontend,
          backend} → shared`, plus transports/agents/runtimes), but decompose
          *work* across those layers into vertical slices: each unit is one
          capability end-to-end, not one whole layer at a time. A slice is
          independently verifiable, so it maps to one convergence pass and one TDD
          cycle (+ an e2e scenario if user-facing). Splitting by layer or dimension
          is for read-only review/research sweeps, not for building.
        - **Test-first (TDD).** New or changed `src/` behavior is driven by its
          mirror unit test (root `AGENT.md`; `tests/AGENT.md`): red (a test that
          fails for the right reason) → green (smallest change that passes) →
          refactor (with the suite green). A public symbol without a test is
          unfinished.
        - **Bounded convergence loop.** When a change spans more than one file or
          can't be finished and verified in one edit, write the plan down, then work
          it in passes: each pass does the next slice (one capability end-to-end),
          runs `make verify`, and commits. Re-derive the worklist from the repo each pass (search before
          assuming something is unbuilt) so progress lives in the tree and the
          commits, not in one ever-growing context; delegate heavy reads to a
          subagent. Stop at the written done-condition, or at a pass cap (default 5
          when the task gives none) — then report done-vs-remaining instead of
          starting another pass.
        - **End-to-end coverage.** A new user-facing flow (route, page, transport
          endpoint) gets a `tests/e2e/` scenario that exercises it through its
          public surface; name it by scenario, not by a source file.
        - **The gate is the judge.** "Done" means `make verify` (`check-all` +
          `lint` + `typecheck` + `test`) is green; phase transitions and completion
          gate on the real exit code, never on a model's self-report.

        These are conventions an agent follows, not gated by a structural check
        today: no check verifies the test mirror, that a test came first, or that
        it exercises the code. The real gate is `make verify` (a red suite fails
        it); TDD itself is a behavioral discipline, not something a static check
        can certify.
        """).strip() + "\n")

    w("AGENT.md", fm(
        title="Root agent rules", kind="rules", layer="n/a",
        status="template", owner="TBD",
        summary="Global rules for any agent working in this repo.") + textwrap.dedent("""
        # Agent rules — repo root

        This file (`AGENT.md`) is the **canonical, vendor-neutral** agent-rules
        file. `CLAUDE.md` is a symlink to it, so Claude Code and any other agent
        tool read the same rules. Edit `AGENT.md`, never the symlink.

        Read **`CONVENTIONS.md`** before doing structural work; it is the source
        of truth for labeling and the directory taxonomy. Each directory's own
        `AGENT.md` adds local rules that override these where more specific.

        ## Always
        - **State new features vendor-agnostically.** When you propose or add a
          capability, design it so no single vendor/provider/tool is baked in:
          put the doer in `scripts/`/`agents/`, keep provider choice behind
          `models/`, and confine vendor-specific wiring to thin adapters
          (see CONVENTIONS §7). Name the neutral concept first; a vendor is one
          interchangeable option.
        - **Respect the `__init__.py` boundary.** Import a package's public
          symbols from the package, never from its private (`_*`) submodules.
          When you add a public symbol, add it to `__all__` and re-export it.
        - **Label new dirs.** A new directory is not done until it has a
          `README.md` and `CLAUDE.md` with valid frontmatter (see CONVENTIONS).
        - **Put code where the taxonomy says.** Transport layers (`api/`,
          `mcp/`) must stay thin and call into `src/`; never duplicate domain
          logic there. Triggers (hooks/schedules) stay thin over
          `scripts/`/`agents/`.
        - **Keep `config/project.json` true.** It is the machine-checked manifest
          of project facts (chosen frontend stack, backend language/version,
          enabled transports); update it when those change — `check_structure.py`
          enforces it (see CONVENTIONS §15).
        - **Mirror unit tests, not the rest.** A new `src/<pkg>/<mod>.py` gets a
          matching `tests/unit/<pkg>/test_<mod>.py`. Integration/e2e tests go
          by scenario.
        - **Work test-first (TDD).** For new or changed `src/` behavior, drive it
          from its mirror test: write/extend the test until it fails for the right
          reason, make it pass with the smallest change, then refactor with the
          suite green. A public symbol with no test is unfinished. (A convention
          you follow — not a structural check; the gate is `make verify`.)
        - **Slice work vertically.** Decompose a task into end-to-end slices —
          each one capability through the layers (`app → {frontend, backend} →
          shared`, plus transports/agents), independently verifiable — not one
          horizontal layer at a time. Each convergence pass should complete one
          slice.
        - **Converge in bounded passes.** When a change spans more than one file or
          can't be finished and verified in a single edit, write the plan down
          first, then each pass: do the next slice (one capability end-to-end), run
          `make verify`, and commit. Re-derive the worklist from the repo each pass
          (search before assuming something is unbuilt) and delegate heavy reads to
          a subagent. Stop at the plan's done-condition — or at a pass cap (default
          5 if the task gives none), and report done-vs-remaining instead of
          starting another pass.
        - **Cover user-facing flows end to end.** A new route, page, or transport
          endpoint gets a `tests/e2e/` scenario that drives it through its public
          surface. (The loops above are disciplines for *you*; the rule is
          CONVENTIONS §17.)
        - **Let the gate decide "done."** A step is finished when `make verify` (or
          the smallest sufficient `make` target) exits green — never on self-report.
        - **Keep docs by purpose**, not by source file (except `docs/reference/`).

        ## Never
        - Reach into another package's internals to "save an import".
        - Add business logic to `api/`, `mcp/`, `scripts/`, or `app/`.
        - Bake a vendor/provider name into a doer — that belongs in a thin adapter.
        - Report work complete (or advance a loop) on your own assessment instead of
          a green `make verify`.
        - Commit secrets to `config/` — only defaults and `*.example.*`.
        """).strip() + "\n")
    symlink_claude("")

    w("pyproject.toml", textwrap.dedent("""
        # Python src-layout. Distribution metadata for Project Keel.
        [build-system]
        requires = ["setuptools>=68", "wheel"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "project_keel"
        version = "0.0.0"
        description = "TODO"
        requires-python = ">=3.10"
        dependencies = []

        [project.optional-dependencies]
        dev = ["pytest", "pytest-cov", "ruff", "mypy"]
        # Optional agent-runtime engines. The default 'inprocess' runtime is pure
        # stdlib (no install); install an engine only if you select it by name,
        # e.g. get_runtime("langgraph"). Keeps the default install dependency-free.
        langgraph = ["langgraph>=0.2"]

        # src-layout: packages live under src/ (importable as their top name).
        [tool.setuptools.packages.find]
        where = ["src"]

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        markers = [
          "unit: fast isolated tests (mirror src/)",
          "integration: 2+ real components",
          "e2e: full-system journeys",
          "smoke: liveness checks",
        ]

        [tool.ruff]
        src = ["src", "tests"]

        [tool.mypy]
        files = ["src"]
        """).strip() + "\n")

    w("Makefile", textwrap.dedent("""
        # Task runner. `make help` lists targets.
        .DEFAULT_GOAL := help
        PY ?= python3

        # Frontend apps = any src/frontend/* that has a package.json. The FE
        # gates iterate over whatever exists, so they are framework-agnostic and
        # a no-op on backend-only repos.
        FE_APPS := $(dir $(wildcard src/frontend/*/package.json))

        .PHONY: help scaffold check check-all check-corpus check-openapi check-aad scaffold-sync verify test unit integration e2e smoke \\
                lint lint-py lint-fe fmt typecheck typecheck-py typecheck-fe \\
                fe-install run run-api run-web site-data demo agent-surface-schema

        help: ## List tasks
        \t@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \\
        \t\tawk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\\n",$$1,$$2}'

        scaffold: ## (Re)generate the skeleton (README/CLAUDE/exemplars)
        \t$(PY) scripts/scaffold.py

        check: ## Validate structure + frontmatter + scaffold embeds (3.6-safe)
        \t$(PY) scripts/check_structure.py
        \t$(PY) scripts/check_scaffold_sync.py --check

        check-all: check check-corpus check-openapi check-aad ## All deterministic checks (project interpreter; see docs/guides/deterministic-checks.md)
        check-corpus: ## Corpus integrity + build determinism (needs python >=3.7)
        \t$(PY) scripts/jobs/check_corpus.py
        check-openapi: ## Committed openapi.json in sync with the app (skips if FastAPI absent)
        \t$(PY) api/rest_fastapi/export_openapi.py --check
        check-aad: ## Committed AAD schema in sync with the model (skips if pydantic absent)
        \t$(PY) scripts/agent_surface/generate_aad_schema.py --check
        scaffold-sync: ## scaffold.py embeds match the live scripts (3.6-safe)
        \t$(PY) scripts/check_scaffold_sync.py --check

        verify: check-all lint typecheck test ## Run all gates (all checks + lint + types + tests)

        test: ## Run the whole test suite
        \t$(PY) -m pytest

        unit: ## Run unit tests only
        \t$(PY) -m pytest -m unit
        integration: ## Run integration tests
        \t$(PY) -m pytest -m integration
        e2e: ## Run end-to-end tests
        \t$(PY) -m pytest -m e2e
        smoke: ## Run smoke tests
        \t$(PY) -m pytest -m smoke

        lint: lint-py lint-fe ## Lint everything (Python + frontend)
        lint-py: ## Lint Python (ruff)
        \truff check src tests
        lint-fe: ## Lint frontend apps (ESLint) — generic to any FE framework
        \t@command -v npm >/dev/null 2>&1 || { echo "npm not found; skipping frontend lint"; exit 0; }
        \t@for app in $(FE_APPS); do \\
        \t\tif [ -d "$$app/node_modules" ]; then echo "eslint: $$app"; (cd $$app && npm run --silent lint) || exit 1; \\
        \t\telse echo "skip $$app (no node_modules — run 'make fe-install')"; fi; \\
        \tdone

        fmt: ## Format Python (ruff)
        \truff format src tests

        typecheck: typecheck-py typecheck-fe ## Type-check everything (Python + frontend)
        typecheck-py: ## Type-check Python (mypy)
        \tmypy src
        typecheck-fe: ## Type-check frontend apps (tsc / astro check)
        \t@command -v npm >/dev/null 2>&1 || { echo "npm not found; skipping frontend typecheck"; exit 0; }
        \t@for app in $(FE_APPS); do \\
        \t\tif [ -d "$$app/node_modules" ]; then echo "typecheck: $$app"; (cd $$app && npm run --silent typecheck) || exit 1; \\
        \t\telse echo "skip $$app (no node_modules — run 'make fe-install')"; fi; \\
        \tdone

        fe-install: ## Install frontend deps for all FE apps
        \t@for app in $(FE_APPS); do echo "npm install: $$app"; (cd $$app && npm install) || exit 1; done

        run: ## Run the app composition root
        \t$(PY) -m app
        site-data: ## Rebuild the wiki corpus the showcase frontend reads
        \t$(PY) scripts/jobs/build_corpus.py
        \t$(PY) scripts/jobs/link_corpus.py
        run-api: ## Serve the showcase REST API (uvicorn :8000; needs the project interpreter)
        \t$(PY) -m uvicorn app:app --app-dir api/rest_fastapi --reload --port 8000
        run-web: ## Serve the showcase frontend (Astro); proxies /api to the backend
        \tcd src/frontend/astro && API_PROXY_TARGET=$${API_PROXY_TARGET:-http://localhost:8000} npm run dev
        demo: ## Run the demo
        \t$(PY) demo/run_demo.py
        agent-surface-schema: ## Regenerate the committed AAD JSON Schema from the model
        \t$(PY) scripts/agent_surface/generate_aad_schema.py
        """).strip() + "\n")

    w(".editorconfig", textwrap.dedent("""
        root = true
        [*]
        charset = utf-8
        end_of_line = lf
        insert_final_newline = true
        trim_trailing_whitespace = true
        indent_style = space
        indent_size = 4
        [*.{js,ts,tsx,json,yml,yaml,md}]
        indent_size = 2
        [Makefile]
        indent_style = tab
        """).strip() + "\n")

    w(".gitignore", textwrap.dedent("""
        __pycache__/
        *.py[cod]
        .pytest_cache/
        .mypy_cache/
        .ruff_cache/
        .venv/
        venv/
        dist/
        build/
        *.egg-info/
        node_modules/
        .astro/
        *.tsbuildinfo
        # generated gRPC stubs
        api/grpc/*_pb2.py
        api/grpc/*_pb2_grpc.py
        # code-doc-monitor (cdmon) generated state — review log, coverage cache
        .cdmon/
        # generated wiki corpus (a view over the repo, never a source of truth)
        wiki/corpus.json
        # durable agent-runtime checkpoints (resume-after-crash snapshots)
        wiki/.runtime/
        .coverage
        coverage.xml
        # local config / secrets
        config/*.local.*
        models/config/*.local.*
        .env
        .env.local
        .claude/settings.local.json
        # model artifacts (track via LFS or external store, not git)
        models/**/*.bin
        models/**/*.safetensors
        models/**/*.ckpt
        """).strip() + "\n")

    w("CONTRIBUTING.md", fm(
        title="Contributing", kind="doc", layer="n/a", status="template",
        owner="TBD", summary="How to add code/tests/docs without breaking the structure.") + textwrap.dedent("""
        # Contributing

        Work in the repo's development loops (test-first, bounded convergence,
        end-to-end coverage); the rule is CONVENTIONS §17. The steps below are
        that discipline applied to one change:

        1. Read `CONVENTIONS.md`.
        2. New package → add `__init__.py` with `__all__`, a `README.md`, and a
           `CLAUDE.md`. Private modules are `_underscore`d.
        3. New public symbol → re-export it from the package `__init__.py`.
        4. New `src/` module → write the mirrored `tests/unit/...` test **first**
           (red), then the code (green), then refactor with the suite green.
        5. New behavior across components → add a `tests/integration` or
           `tests/e2e` scenario and (if user-facing) a `test-docs/` plan entry.
        6. Run `make verify` (the full gate) — or at least `make lint test` —
           before pushing; treat green as the definition of done.
        """).strip() + "\n")

    w("CHANGELOG.md", "# Changelog\n\nAll notable changes. Format: Keep a Changelog.\n\n## [Unreleased]\n- Initial template.\n")
    w("LICENSE", "TODO: choose a license (MIT/Apache-2.0/proprietary) and paste its text here.\n")


def hidden_files():
    """Committed dot-files/dirs only — caches/secrets stay gitignored (CONVENTIONS §5)."""
    w(".env.example", textwrap.dedent("""
        # Required environment variables (NO real values here). Copy to .env (gitignored).
        # Secrets such as model API keys are read from the environment, never committed.
        ANTHROPIC_API_KEY=
        LOG_LEVEL=info
        """).strip() + "\n")

    w(".gitattributes", textwrap.dedent("""
        * text=auto eol=lf
        # Large model artifacts via LFS (uncomment if you use git-lfs):
        # *.safetensors filter=lfs diff=lfs merge=lfs -text
        # *.bin         filter=lfs diff=lfs merge=lfs -text
        """).strip() + "\n")

    # CI — GitHub Actions by default; swap for .gitlab-ci.yml if you use GitLab.
    w(".github/workflows/ci.yml", textwrap.dedent("""
        name: ci
        on: [push, pull_request]
        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-python@v5
                with: { python-version: "3.11" }
              - uses: actions/setup-node@v4
                with: { node-version: "22" }
              - run: pip install -e ".[dev]"
              # Install FE deps so the frontend lint/typecheck gates run; no-op
              # if there are no frontend apps.
              - run: make fe-install
              - run: make check-all
              - run: make lint
              - run: make typecheck
              - run: make test
        """).strip() + "\n")

    # Team-shared agent config.
    w(".claude/settings.json", textwrap.dedent("""
        {
          "$comment": "Team-shared Claude Code settings. Personal overrides go in settings.local.json (gitignored)."
        }
        """).strip() + "\n")
    w(".claude/README.md", fm(
        title=".claude", kind="config", layer="n/a", status="template",
        owner="TBD", summary="Team-shared Claude Code config (settings, skills, commands).") +
      "\n# `.claude/`\n\nTeam-shared agent configuration: `settings.json`, plus "
      "optional `skills/` and `commands/`. Personal, machine-local settings go "
      "in `settings.local.json` (gitignored). This dir holds *decisions* shared "
      "with the team, so it is committed — unlike caches and `.env`.\n")


# --------------------------------------------------------------------------- #
# src/ tree with the real exemplar code
# --------------------------------------------------------------------------- #
def src_tree():
    readme("src", title="Source", kind="package", layer="n/a",
           summary="All production source, split by layer.",
           body="""
           Layers (see `CONVENTIONS.md`):

           - `frontend/` — UI / client.
           - `backend/` — server, domain, services.
           - `shared/` — contracts/types used by both FE and BE.
           - `app/` — composition root: entrypoints, wiring, CLI/`__main__`.

           Dependency direction: `app/` → (`frontend/`, `backend/`) → `shared/`.
           `shared/` depends on nothing else here. `frontend/` and `backend/`
           never import each other directly — they meet through `shared/`
           contracts and the `app/` wiring.
           """)
    claude("src", title="src", layer="n/a", rules=[
        "**Every export crosses an `__init__.py`.** Add public symbols to "
        "`__all__` and re-export them; keep implementation in `_*` modules.",
        "**Drive new behavior with its test (TDD).** Before adding or changing a "
        "public symbol, write/extend its `tests/unit/...` mirror so it fails "
        "first, then make it pass, then refactor with the suite green "
        "(CONVENTIONS §17).",
        "Respect the dependency direction: `app → {frontend, backend} → shared`. "
        "No back-edges, no FE↔BE direct imports.",
        "`shared/` must stay framework-free and import nothing else in `src/`.",
        "Each package needs a `shared/` only if it has domain-shared code, and a "
        "`util/` only if it has generic helpers — don't create empty ones.",
    ])

    # ---- frontend: two real, type-strict reference apps ----
    readme("src/frontend", title="Frontend", kind="package", layer="frontend",
           public_api="each app's src/index.ts barrel",
           summary="UI / client code. Two reference apps — keep one, delete the other.",
           body="""
           UI only — no domain/server logic (that lives in `backend/`, shared
           contracts in `shared/`). Two complete, type-strict reference apps
           ship here; a real project keeps **one** and deletes the other:

           | App | Use it for | Stack |
           |-----|-----------|-------|
           | `react-vite/` | an interactive SPA that talks to `backend/` | Vite + React 19 + TS (strict) + Tailwind v4 + ESLint |
           | `astro/` | a content/marketing site, mostly static pages | Astro 5 + TS (strict) + Tailwind v4 + ESLint |

           Both are wired to be **type-strict** (`strict` + `noUncheckedIndexedAccess`
           + `exactOptionalPropertyTypes` etc.) and linted with a flat
           `eslint.config.js`. The **public-API boundary** is each app's
           `src/index.ts` **barrel** — the TS analog of Python's `__init__.py`:
           other code imports from the barrel, never from deep paths. The
           React app shows importing the FE-side mirror of the backend `shared`
           contract (`src/types.ts`).
           """)
    claude("src/frontend", title="frontend", layer="frontend", rules=[
        "No business rules here — call the backend/API; render results.",
        "Each app's public surface is its `src/index.ts` barrel (the `__init__.py` "
        "analog). Import from the barrel, never deep paths.",
        "Keep TypeScript strict: do not weaken `tsconfig` (`strict`, "
        "`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) to silence "
        "errors — fix the types.",
        "FE types that mirror the backend `shared` contract should be generated "
        "from it (or OpenAPI), not hand-drifted. One source of truth.",
        "A real project keeps ONE of `react-vite/` / `astro/`; delete the other.",
    ])
    frontend_react_vite("src/frontend/react-vite")
    frontend_astro("src/frontend/astro")


# --------------------------------------------------------------------------- #
# frontend app generators
# --------------------------------------------------------------------------- #
def frontend_react_vite(base):
    readme(base, title="Frontend — React + Vite", kind="package",
           layer="frontend", public_api=f"{base}/src/index.ts",
           summary="Type-strict Vite + React 19 + Tailwind v4 + ESLint SPA.",
           body="""
           Interactive SPA that talks to `backend/`. Commands: `npm run dev`
           (Vite dev server), `npm run build` (`tsc -b && vite build`),
           `npm run lint`, `npm run typecheck`.

           - **Boundary:** `src/index.ts` re-exports the app's public surface;
             `src/main.tsx` mounts via that barrel.
           - **Contract:** `src/types.ts` mirrors the backend `shared` contract
             (`Thing`). Generate these from the contract/OpenAPI in a real app.
           - **Type-strict:** see `tsconfig.app.json`.
           - **Lint:** flat `eslint.config.js` with `typescript-eslint`
             `strictTypeChecked` + React Hooks rules.
           - **Tailwind v4:** via `@tailwindcss/vite`; `@import "tailwindcss"`
             in `src/index.css`.
           """)
    claude(base, title="frontend/react-vite", layer="frontend", rules=[
        "Import the app's public symbols from `src/index.ts`, not deep paths.",
        "Keep `tsconfig.app.json` strict; fix types rather than loosening flags.",
        "Components are typed (`interface Props`) and presentational — no domain "
        "logic; call the API.",
        "Style with Tailwind utility classes; don't add a second CSS system.",
    ])
    w(f"{base}/package.json", textwrap.dedent('''
        {
          "name": "frontend-react-vite",
          "private": true,
          "version": "0.0.0",
          "type": "module",
          "scripts": {
            "dev": "vite",
            "build": "tsc -b && vite build",
            "preview": "vite preview",
            "lint": "eslint .",
            "typecheck": "tsc -b --noEmit"
          },
          "dependencies": {
            "react": "^19.0.0",
            "react-dom": "^19.0.0"
          },
          "devDependencies": {
            "@eslint/js": "^9.17.0",
            "@tailwindcss/vite": "^4.0.0",
            "@types/react": "^19.0.0",
            "@types/react-dom": "^19.0.0",
            "@vitejs/plugin-react": "^4.3.4",
            "eslint": "^9.17.0",
            "eslint-plugin-react-hooks": "^5.1.0",
            "eslint-plugin-react-refresh": "^0.4.16",
            "globals": "^15.14.0",
            "tailwindcss": "^4.0.0",
            "typescript": "~5.7.2",
            "typescript-eslint": "^8.18.0",
            "vite": "^6.0.5"
          }
        }
        ''').strip() + "\n")
    w(f"{base}/tsconfig.json", textwrap.dedent('''
        {
          "files": [],
          "references": [
            { "path": "./tsconfig.app.json" },
            { "path": "./tsconfig.node.json" }
          ]
        }
        ''').strip() + "\n")
    w(f"{base}/tsconfig.app.json", textwrap.dedent('''
        {
          "compilerOptions": {
            "target": "ES2022",
            "useDefineForClassFields": true,
            "lib": ["ES2022", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "moduleResolution": "bundler",
            "jsx": "react-jsx",
            "skipLibCheck": true,
            "noEmit": true,
            "isolatedModules": true,
            "verbatimModuleSyntax": true,

            "strict": true,
            "noUnusedLocals": true,
            "noUnusedParameters": true,
            "noFallthroughCasesInSwitch": true,
            "noUncheckedIndexedAccess": true,
            "noImplicitOverride": true,
            "exactOptionalPropertyTypes": true
          },
          "include": ["src"]
        }
        ''').strip() + "\n")
    w(f"{base}/tsconfig.node.json", textwrap.dedent('''
        {
          "compilerOptions": {
            "target": "ES2022",
            "lib": ["ES2023"],
            "module": "ESNext",
            "moduleResolution": "bundler",
            "skipLibCheck": true,
            "noEmit": true,
            "isolatedModules": true,
            "strict": true
          },
          "include": ["vite.config.ts"]
        }
        ''').strip() + "\n")
    w(f"{base}/vite.config.ts", textwrap.dedent('''
        import { defineConfig } from 'vite'
        import react from '@vitejs/plugin-react'
        import tailwindcss from '@tailwindcss/vite'

        export default defineConfig({
          plugins: [react(), tailwindcss()],
        })
        ''').strip() + "\n")
    w(f"{base}/eslint.config.js", textwrap.dedent('''
        import js from '@eslint/js'
        import globals from 'globals'
        import reactHooks from 'eslint-plugin-react-hooks'
        import reactRefresh from 'eslint-plugin-react-refresh'
        import tseslint from 'typescript-eslint'

        export default tseslint.config(
          { ignores: ['dist'] },
          {
            extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
            files: ['**/*.{ts,tsx}'],
            languageOptions: {
              ecmaVersion: 2022,
              globals: globals.browser,
              parserOptions: {
                project: ['./tsconfig.app.json', './tsconfig.node.json'],
                tsconfigRootDir: import.meta.dirname,
              },
            },
            plugins: {
              'react-hooks': reactHooks,
              'react-refresh': reactRefresh,
            },
            rules: {
              ...reactHooks.configs.recommended.rules,
              'react-refresh/only-export-components': [
                'warn',
                { allowConstantExport: true },
              ],
            },
          },
        )
        ''').strip() + "\n")
    w(f"{base}/index.html", textwrap.dedent('''
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Frontend — React + Vite</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
          </body>
        </html>
        ''').strip() + "\n")
    w(f"{base}/src/index.css", '@import "tailwindcss";\n')
    w(f"{base}/src/index.ts", textwrap.dedent('''
        // Public API barrel for this app — the TS analog of Python's __init__.py.
        // Other code imports from here, never from deep paths.
        export { App } from './App'
        export type { Thing } from './types'
        ''').strip() + "\n")
    w(f"{base}/src/types.ts", textwrap.dedent('''
        // FE-side mirror of the backend `shared` contract (Python: src/shared).
        // In a TS-backed project, GENERATE these from the shared contract or
        // OpenAPI instead of hand-writing them — keep one source of truth.
        export interface Thing {
          readonly name: string
          readonly value: number
        }
        ''').strip() + "\n")
    w(f"{base}/src/main.tsx", textwrap.dedent('''
        import { StrictMode } from 'react'
        import { createRoot } from 'react-dom/client'
        import { App } from './index'
        import './index.css'

        const root = document.getElementById('root')
        if (!root) throw new Error('missing #root element')

        createRoot(root).render(
          <StrictMode>
            <App />
          </StrictMode>,
        )
        ''').strip() + "\n")
    w(f"{base}/src/App.tsx", textwrap.dedent('''
        import { useState } from 'react'
        import { Button } from './components/Button'
        import type { Thing } from './types'

        export function App(): React.JSX.Element {
          const [thing, setThing] = useState<Thing>({ name: 'hello', value: 0 })

          return (
            <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-8">
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">
                {thing.name}: {thing.value}
              </h1>
              <Button
                onClick={() => {
                  setThing((t) => ({ ...t, value: t.value + 1 }))
                }}
              >
                increment
              </Button>
            </main>
          )
        }
        ''').strip() + "\n")
    w(f"{base}/src/components/Button.tsx", textwrap.dedent('''
        import type { ReactNode } from 'react'

        interface ButtonProps {
          readonly children: ReactNode
          readonly onClick: () => void
        }

        export function Button({ children, onClick }: ButtonProps): React.JSX.Element {
          return (
            <button
              type="button"
              onClick={onClick}
              className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              {children}
            </button>
          )
        }
        ''').strip() + "\n")


def frontend_astro(base):
    readme(base, title="Frontend — Astro (static)", kind="package",
           layer="frontend", public_api=f"{base}/src/pages",
           summary="Type-strict Astro 5 + Tailwind v4 + ESLint static site.",
           body="""
           Content/marketing site — mostly static, pre-rendered HTML with zero
           JS by default. Commands: `npm run dev`, `npm run build`,
           `npm run preview`, `npm run lint`, `npm run typecheck` (`astro check`).

           - **Routing:** files in `src/pages/` are the public surface (routes).
           - **Type-strict:** extends `astro/tsconfigs/strict`, plus
             `noUncheckedIndexedAccess` / `noImplicitOverride`.
           - **Lint:** flat `eslint.config.js` with `typescript-eslint` +
             `eslint-plugin-astro`.
           - **Tailwind v4:** via `@tailwindcss/vite` in `astro.config.mjs`;
             `@import "tailwindcss"` in `src/styles/global.css`.
           """)
    claude(base, title="frontend/astro", layer="frontend", rules=[
        "Pages in `src/pages/` are routes — keep them thin; push markup into "
        "`src/components/` and `src/layouts/`.",
        "Keep it static-first: no client JS unless a component genuinely needs "
        "interactivity (then use an island explicitly).",
        "Keep TS strict (`astro/tsconfigs/strict`); type `Astro.props` via a "
        "`Props` interface in each component.",
        "Style with Tailwind utilities; global CSS only imports Tailwind.",
    ])
    w(f"{base}/package.json", textwrap.dedent('''
        {
          "name": "frontend-astro",
          "private": true,
          "version": "0.0.0",
          "type": "module",
          "scripts": {
            "dev": "astro dev",
            "build": "astro build",
            "preview": "astro preview",
            "lint": "eslint .",
            "typecheck": "astro check"
          },
          "dependencies": {
            "astro": "^5.1.0"
          },
          "devDependencies": {
            "@eslint/js": "^9.17.0",
            "@tailwindcss/vite": "^4.0.0",
            "eslint": "^9.17.0",
            "eslint-plugin-astro": "^1.3.1",
            "globals": "^15.14.0",
            "tailwindcss": "^4.0.0",
            "typescript": "~5.7.2",
            "typescript-eslint": "^8.18.0"
          }
        }
        ''').strip() + "\n")
    w(f"{base}/tsconfig.json", textwrap.dedent('''
        {
          "extends": "astro/tsconfigs/strict",
          "include": [".astro/types.d.ts", "**/*"],
          "exclude": ["dist"],
          "compilerOptions": {
            "noUncheckedIndexedAccess": true,
            "noImplicitOverride": true
          }
        }
        ''').strip() + "\n")
    w(f"{base}/astro.config.mjs", textwrap.dedent('''
        import { defineConfig } from 'astro/config'
        import tailwindcss from '@tailwindcss/vite'

        export default defineConfig({
          vite: {
            plugins: [tailwindcss()],
          },
        })
        ''').strip() + "\n")
    w(f"{base}/eslint.config.js", textwrap.dedent('''
        import js from '@eslint/js'
        import tseslint from 'typescript-eslint'
        import astro from 'eslint-plugin-astro'

        export default tseslint.config(
          { ignores: ['dist', '.astro'] },
          js.configs.recommended,
          ...tseslint.configs.recommended,
          ...astro.configs.recommended,
        )
        ''').strip() + "\n")
    w(f"{base}/src/styles/global.css", '@import "tailwindcss";\n')
    w(f"{base}/src/layouts/Layout.astro", textwrap.dedent('''
        ---
        import '../styles/global.css'

        interface Props {
          readonly title: string
        }

        const { title } = Astro.props
        ---

        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>{title}</title>
          </head>
          <body class="bg-slate-50 text-slate-900">
            <slot />
          </body>
        </html>
        ''').strip() + "\n")
    w(f"{base}/src/components/Card.astro", textwrap.dedent('''
        ---
        interface Props {
          readonly title: string
          readonly body: string
        }

        const { title, body } = Astro.props
        ---

        <article class="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-xl font-semibold">{title}</h2>
          <p class="mt-2 text-slate-600">{body}</p>
        </article>
        ''').strip() + "\n")
    w(f"{base}/src/pages/index.astro", textwrap.dedent('''
        ---
        import Layout from '../layouts/Layout.astro'
        import Card from '../components/Card.astro'

        const features = [
          { title: 'Static', body: 'Pre-rendered HTML, zero JS by default.' },
          { title: 'Type-strict', body: 'astro/tsconfigs/strict + ESLint.' },
          { title: 'Tailwind v4', body: 'Utility CSS via the Vite plugin.' },
        ] as const
        ---

        <Layout title="Astro static site">
          <main class="mx-auto max-w-3xl p-8">
            <h1 class="mb-8 text-4xl font-bold tracking-tight">Astro static pages</h1>
            <div class="grid gap-4 sm:grid-cols-3">
              {features.map((f) => <Card title={f.title} body={f.body} />)}
            </div>
          </main>
        </Layout>
        ''').strip() + "\n")

    # ---- backend: the fully-worked Python exemplar ----
    readme("src/backend", title="Backend", kind="package", layer="backend",
           public_api="src/backend/__init__.py",
           summary="Server / domain / services.",
           body="""
           The worked exemplar of the conventions. Structure:

           | Path | Role |
           |------|------|
           | `__init__.py` | **public API** — the only thing callers import |
           | `contracts.py` | ABCs / Protocols (the cross-package interfaces) |
           | `example_feature/` | a sample feature package (rename me) |
           | `shared/` | domain-shared types/models |
           | `util/` | generic, domain-agnostic helpers |

           Note how `example_feature/__init__.py` re-exports `do_thing` and
           `Thing` and hides `_impl.py`. Callers do
           `from backend import do_thing` — never `from backend.example_feature._impl import ...`.
           """)
    claude("src/backend", title="backend", layer="backend", rules=[
        "The public API is `__init__.py`/`__all__`. Implementation lives in "
        "`_*` modules and is never imported across package boundaries.",
        "Define interfaces as ABCs/Protocols in `contracts.py`; depend on the "
        "contract, not the concrete class. Add new ABCs here, not inline.",
        "No transport concerns (HTTP/MCP/CLI) in here — those live in "
        "`api/`, `mcp/`, `app/` and call into this package.",
    ])

    w("src/backend/__init__.py", textwrap.dedent('''
        """
        title: Backend public API
        layer: backend
        public_api: yes
        summary: The only import surface for the backend package.
        """
        # Re-export the public surface. Callers import FROM HERE, never from
        # private submodules. Keep __all__ tight and intentional.
        from .contracts import Repository, Service
        from .example_feature import Thing, do_thing

        __all__ = ["Repository", "Service", "Thing", "do_thing"]
        ''').strip() + "\n")

    w("src/backend/contracts.py", textwrap.dedent('''
        """
        title: Backend contracts
        layer: backend
        public_api: yes
        summary: ABCs / Protocols that define cross-package interfaces.
        """
        from __future__ import annotations
        from abc import ABC, abstractmethod
        from typing import Protocol, runtime_checkable

        __all__ = ["Repository", "Service"]


        @runtime_checkable
        class Repository(Protocol):
            """A storage boundary. Structural: anything with these methods qualifies."""

            def get(self, key: str) -> object | None: ...
            def put(self, key: str, value: object) -> None: ...


        class Service(ABC):
            """A unit of backend behavior. Depend on this, not on concretes."""

            @abstractmethod
            def handle(self, request: object) -> object:
                """Process a request and return a result."""
                raise NotImplementedError
        ''').strip() + "\n")

    w("src/backend/example_feature/__init__.py", textwrap.dedent('''
        """
        title: Example feature
        layer: backend
        public_api: yes
        summary: Sample feature package showing the __init__-as-API boundary.
        """
        from ._impl import Thing, do_thing  # implementation hidden behind the barrel

        __all__ = ["Thing", "do_thing"]
        ''').strip() + "\n")

    w("src/backend/example_feature/_impl.py", textwrap.dedent('''
        """
        title: Example feature implementation (private)
        layer: backend
        public_api: no
        summary: Private impl. Never imported across the package boundary.
        """
        from dataclasses import dataclass

        __all__ = ["Thing", "do_thing"]


        @dataclass(frozen=True)
        class Thing:
            """An example domain value object. Replace with your real type."""
            name: str
            value: int = 0


        def do_thing(name: str, value: int = 0) -> Thing:
            """Create a Thing. Replace with your real feature logic."""
            return Thing(name=name, value=value)
        ''').strip() + "\n")

    w("src/backend/shared/__init__.py", textwrap.dedent('''
        """
        title: Backend shared
        layer: backend
        public_api: yes
        summary: Domain-meaningful types/models shared across backend features.
        """
        __all__: list[str] = []
        ''').strip() + "\n")

    w("src/backend/util/__init__.py", textwrap.dedent('''
        """
        title: Backend util
        layer: backend
        public_api: yes
        summary: Generic, domain-agnostic helpers (no domain knowledge here).
        """
        __all__: list[str] = []
        ''').strip() + "\n")

    # ---- shared (cross-cutting FE+BE) ----
    readme("src/shared", title="Shared (the FE<->BE contract)", kind="package",
           layer="shared", public_api="src/shared/__init__.py",
           summary="The data contract both frontend and backend agree on.",
           body="""
           This is the **contract between frontend and backend** — the shapes
           both sides must agree on: DTOs / request-response models, enums,
           error codes, validation rules. It is the *vocabulary*, not the wire.

           Distinguish carefully:

           - `shared/` (here) — the agreed **data shapes**. "A Thing has
             `{name, value}`." Framework-free.
           - `api/` (top-level) — the **transport** that carries those shapes
             over HTTP. Imports `shared/`; `shared/` never imports it.
           - `util/` — generic helpers with no domain meaning. Not this.

           Must not import from `frontend/`, `backend/`, `app/`, or any
           framework. Both sides depend on it; it depends on nothing in `src/`.
           """)
    claude("src/shared", title="shared", layer="shared", rules=[
        "This is the FE<->BE data contract (DTOs/enums/error codes), NOT "
        "transport (that's `api/`) and NOT generic helpers (that's `util/`).",
        "Framework-free and dependency-free w.r.t. the rest of `src/`. Other "
        "layers import it; it imports nothing here.",
        "Only put things BOTH frontend and backend need. If only one needs it, "
        "it belongs in that layer's own `shared/`.",
        "Public surface via `__init__.py`/`__all__`.",
    ])
    w("src/shared/__init__.py", textwrap.dedent('''
        """
        title: Shared cross-cutting contracts
        layer: shared
        public_api: yes
        summary: DTOs/enums/error codes shared by frontend and backend.
        """
        __all__: list[str] = []
        ''').strip() + "\n")

    # ---- app (composition root) — OPTIONAL ----
    readme("src/app", title="App (composition root) — OPTIONAL", kind="package",
           layer="app", public_api="src/app/__init__.py",
           summary="OPTIONAL single-process composition root. Delete it for client-server web apps.",
           body="""
           **Optional. Keep it only if one process wires the layers together.**

           `app/` is a *composition root*: dependency injection, config loading,
           CLI/`__main__`, server bootstrap. **No business logic** — it only
           wires `backend`/`frontend`/`shared` and starts them.

           Two archetypes decide whether you need it:

           | Project | Entrypoint | Keep `app/`? |
           |---------|-----------|--------------|
           | **Client-server web** (separate FE build + BE server) | FE = its own build; BE = its server (`api/`/`backend/`) | **No** — nothing imports both in one process. Delete this dir. |
           | **Single-process** (CLI, service, library) | one `__main__`/`bin` that wires everything | **Yes** — that wiring *is* this dir. |

           genbuild is the single-process kind (a CLI, no `frontend/`), so it
           has an `app/`-equivalent in `bin/`. A React+API product is the first
           kind, so it has no `app/`. `make run` calls `python -m app`.
           """)
    claude("src/app", title="app", layer="app", rules=[
        "OPTIONAL. If frontend and backend are separate deployables (client-"
        "server web), there is no single-process root — delete this dir.",
        "Wiring only — construct concretes, inject them via `contracts`, start "
        "the process. No domain logic.",
        "This is the ONLY layer allowed to import from both `frontend` and "
        "`backend`.",
        "Read config from `config/`; never hardcode environment specifics.",
    ])
    w("src/app/__init__.py", '"""title: App composition root\nlayer: app\npublic_api: yes\nsummary: Wiring + entrypoints.\n"""\n__all__: list[str] = []\n')
    w("src/app/__main__.py", textwrap.dedent('''
        """
        title: App entrypoint
        layer: app
        public_api: no
        summary: `python -m app` — wire dependencies and run.
        """
        from backend import do_thing


        def main() -> int:
            thing = do_thing("hello", 1)
            print(f"composed and ran: {thing}")
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        ''').strip() + "\n")


# --------------------------------------------------------------------------- #
# tests/ — unit mirrors src, the rest by scenario
# --------------------------------------------------------------------------- #
def tests_tree():
    readme("tests", title="Tests", kind="tests", layer="n/a",
           summary="Unit tests mirror src/; integration/e2e/smoke go by scenario.",
           body="""
           | Subdir | Mirrors `src/`? | Organize by |
           |--------|-----------------|-------------|
           | `unit/` | **Yes, 1:1** | source module |
           | `integration/` | No | scenario (2+ real components) |
           | `e2e/` | No | user journey |
           | `smoke/` | No | liveness check |

           `fixtures/` holds shared data; `conftest.py` holds shared pytest
           fixtures. Markers (`unit`/`integration`/`e2e`/`smoke`) are declared
           in `pyproject.toml` — select with `pytest -m`.
           """)
    claude("tests", title="tests", layer="n/a", rules=[
        "A new `src/<pkg>/<mod>.py` REQUIRES a mirrored "
        "`tests/unit/<pkg>/test_<mod>.py`.",
        "A new user-facing flow (route, page, or transport endpoint) gets a "
        "`tests/e2e/` scenario that drives it through the public surface — author "
        "it alongside the change, not later (CONVENTIONS §17).",
        "Do NOT mirror integration/e2e/smoke to source files — name them by the "
        "scenario under test.",
        "Unit tests touch no network/disk/process. If you need those, it's an "
        "integration test.",
        "Test through the package's public API (`__init__`), not its `_*` "
        "internals — tests are callers too.",
    ])
    w("tests/conftest.py", '"""Shared pytest fixtures live here."""\n')
    keep("tests/fixtures")

    # mirrored unit test for the backend exemplar
    w("tests/unit/backend/test_example_feature.py", textwrap.dedent('''
        """
        title: Unit — backend.example_feature
        kind: tests
        layer: backend
        summary: Mirrors src/backend/example_feature/. Tests via the public API.
        """
        import pytest
        from backend import do_thing, Thing  # public API, not _impl

        pytestmark = pytest.mark.unit


        def test_do_thing_returns_thing():
            t = do_thing("x", 3)
            assert isinstance(t, Thing)
            assert t.name == "x" and t.value == 3
        ''').strip() + "\n")
    w("tests/unit/README.md", fm(
        title="Unit tests", kind="tests", layer="n/a", status="template",
        owner="TBD", summary="Mirrors src/ 1:1.") +
      "\n# Unit tests\n\nMirror `src/` exactly: `src/backend/example_feature/_impl.py` "
      "→ `tests/unit/backend/test_example_feature.py`. Test via the public API.\n")

    for sub, desc in [
        ("integration", "Two or more real components together, named by scenario."),
        ("e2e", "Full-system user journeys end to end."),
        ("smoke", "Fast post-deploy liveness checks."),
    ]:
        w(f"tests/{sub}/README.md", fm(
            title=f"{sub.title()} tests", kind="tests", layer="n/a",
            status="template", owner="TBD", summary=desc) +
          f"\n# {sub.title()} tests\n\n{desc} Do **not** mirror source files — one "
          f"file per scenario.\n")
        keep(f"tests/{sub}")


# --------------------------------------------------------------------------- #
# test-docs/
# --------------------------------------------------------------------------- #
def test_docs_tree():
    readme("test-docs", title="Test docs", kind="test-doc", layer="n/a",
           summary="Test plans, coverage register, and overall test strategy.",
           body="""
           Planning *about* tests (the tests themselves live in `tests/`).

           - `strategy.md` — what we test, at which level, and why.
           - `test-plan/` — one plan per module/feature (loosely mirrors
             `tests/`, not `src/` file-for-file).
           - `coverage/` — a living register mapping acceptance criteria →
             scenarios → covered/not.
           """)
    claude("test-docs", title="test-docs", layer="n/a", rules=[
        "Plans describe intent and acceptance criteria; they don't duplicate "
        "test code.",
        "Keep the coverage register in sync when you add/remove scenarios.",
        "Organize by test level and feature, not by source file.",
    ])
    w("test-docs/strategy.md", fm(
        title="Test strategy", kind="test-doc", layer="n/a", status="template",
        owner="TBD", summary="What we test at each level and why.") +
      "\n# Test strategy\n\n- **Unit** (mirrors `src/`): logic in isolation.\n"
      "- **Integration**: real component seams.\n- **E2E**: user journeys.\n"
      "- **Smoke**: liveness.\n\nDefine the risk-based rationale for the split here.\n")
    w("test-docs/test-plan/README.md", fm(
        title="Test plans", kind="test-doc", layer="n/a", status="template",
        owner="TBD", summary="One plan per module/feature.") +
      "\n# Test plans\n\nOne file per module/feature, e.g. "
      "`backend.example_feature.md`. Each lists scenarios, acceptance criteria, "
      "and the level (unit/integration/e2e) each is covered at.\n")
    w("test-docs/coverage/register.md", fm(
        title="Coverage register", kind="test-doc", layer="n/a",
        status="template", owner="TBD",
        summary="Living map: acceptance criterion -> scenario -> status.") +
      "\n# Coverage register\n\n| Criterion | Scenario | Level | Status |\n"
      "|-----------|----------|-------|--------|\n"
      "| example: do_thing creates a Thing | test_do_thing_returns_thing | unit | ✅ |\n")


# --------------------------------------------------------------------------- #
# docs/ — by purpose
# --------------------------------------------------------------------------- #
def docs_tree():
    readme("docs", title="Docs", kind="doc", layer="n/a",
           summary="Documentation organized by purpose and audience, not by source file.",
           body="""
           | Subdir | Audience | Content |
           |--------|----------|---------|
           | `architecture/` | builders | system shape, components, data flow |
           | `specs/` | builders/QA | requirements + acceptance criteria |
           | `design/` | builders | per-feature design, task breakdown, contracts |
           | `guides/` | users + new devs | user guides, engineering guides, how-tos |
           | `reference/` | everyone | per-module reference (the only part that thinly mirrors `src/`) |
           | `adr/` | builders | Architecture Decision Records (numbered, immutable) |
           """)
    claude("docs", title="docs", layer="n/a", rules=[
        "Organize by purpose/audience, never by source file — except "
        "`reference/`, which may thinly mirror packages.",
        "ADRs are immutable once accepted: supersede, don't edit.",
        "Each doc carries frontmatter (`kind: doc|spec|design|adr`).",
    ])
    for sub, desc in [
        ("architecture", "System-level shape: components, boundaries, data flow, tech choices."),
        ("specs", "Requirements and acceptance criteria with traceability."),
        ("design", "Per-feature technical design, task decomposition, code contracts."),
        ("guides", "User guides, engineering guides, runnable how-tos."),
        ("reference", "Per-module reference. The only docs that may thinly mirror src/."),
    ]:
        w(f"docs/{sub}/README.md", fm(
            title=sub.title(), kind="doc", layer="n/a", status="template",
            owner="TBD", summary=desc) + f"\n# {sub.title()}\n\n{desc}\n")
    w("docs/adr/0001-record-architecture-decisions.md", fm(
        title="ADR-0001: Record architecture decisions", kind="adr",
        layer="n/a", status="accepted", owner="TBD",
        summary="We will record architecturally significant decisions as ADRs.") +
      textwrap.dedent("""
        # ADR-0001: Record architecture decisions

        **Status:** accepted

        ## Context
        Architecturally significant decisions get lost in chat and commits.

        ## Decision
        Record each as a numbered, immutable ADR in `docs/adr/`. Supersede
        rather than edit.

        ## Consequences
        A durable, reviewable decision log. New ADRs reference the ones they
        supersede.
        """).strip() + "\n")

    w("docs/architecture/transports.md", fm(
        title="API transports", kind="doc", layer="n/a", status="template",
        owner="TBD", tags=["api", "transport", "architecture"],
        summary="How clients reach the domain: the edge + transport layers in api/.") +
      textwrap.dedent("""
        # API transports

        Clients never touch the domain directly. Requests flow inward through
        thin layers; only `src/` holds business logic.

        ```
        client ──HTTP/HTTPS──> edge (nginx)  ──> transport ──> src/ (domain)
                               TLS, redirect       │
                                                   ├─ REST/OpenAPI  (api/rest_fastapi)
                                                   └─ gRPC          (api/grpc)
        ```

        | Layer | Lives in | Responsibility | Must NOT |
        |-------|----------|----------------|----------|
        | Edge | `api/edge_nginx/` (or `ops/`) | TLS termination, HTTP->HTTPS, reverse proxy | hold app logic |
        | Transport | `api/rest_fastapi/`, `api/grpc/` | (de)serialize the wire, validate, delegate | hold domain logic |
        | Domain | `src/` | the actual behavior | know about HTTP/gRPC |

        ## Choosing a transport
        - **REST + OpenAPI (FastAPI)** — public/3rd-party HTTP clients, browsers,
          self-documenting JSON. The default.
        - **gRPC** — service-to-service, low latency, streaming, strict schemas.
        - **GraphQL / WebSockets / queues** — add a sibling `api/<style>/`
          following the same thin-over-`src/` rule.

        ## The contract is single-sourced
        HTTP DTOs (`schemas.py`) and proto messages (`thing.proto`) **mirror**
        `src/shared/`. Don't redefine the contract per transport — generate or
        derive it, and keep the OpenAPI doc / `.proto` checked in and in sync.
        """).strip() + "\n")


# --------------------------------------------------------------------------- #
# the operational/peripheral top-level dirs
# --------------------------------------------------------------------------- #
def peripheral_dirs():
    specs = {
        "agents": dict(
            kind="agent",
            summary="Autonomous / LLM agents (the 'brains') — reasoning, policy, prompts.",
            body="""
            Each agent is the decision-making core: prompts, policy, tool-use
            logic. An agent needs a *model* to run on — it gets one from
            `models/` (`get_model(name).run(prompt)`), so it never hardcodes a
            provider. Keep transport (how the agent is *reached*) out of here —
            that's `mcp/` and `api/`. Agents call into `src/` for real work and
            into `evals/` for scoring. Default any state-changing action to a
            dry run unless explicitly authorized.
            """,
            rules=[
                "Agents hold reasoning/policy/prompts only; they call `src/` for "
                "domain work and never embed transport code.",
                "Get the model from `models/` (`get_model`), never hardcode a "
                "provider or model id in the agent.",
                "State-changing actions default to dry-run; require explicit "
                "authorization to execute.",
                "Expose agents to the world via `mcp/` or `api/`, not by "
                "importing transport here.",
            ]),
        "mcp": dict(
            kind="mcp",
            summary="Model Context Protocol servers — tool gateways over the app.",
            body="""
            Thin MCP servers that expose `src/`/`agents/` capabilities as tools.
            Split read-only (Q&A) from state-changing (action) servers; the
            action server defaults to dry-run. No business logic here — validate,
            translate, and delegate.
            """,
            rules=[
                "Keep servers thin: validate + delegate into `src/`/`agents/`. "
                "No domain logic.",
                "Separate Q&A (read-only) from action (state-changing) servers; "
                "action defaults to dry-run.",
                "Every tool gets a schema and a one-line description.",
            ]),
        "api": dict(
            kind="api",
            summary="API transports over the domain — REST/OpenAPI (FastAPI), gRPC, and the nginx edge. All thin over src/.",
            body="""
            The network surface. Every transport here is a **thin adapter** that
            translates a wire protocol into calls on the `src/` public API; the
            request/response shapes mirror `src/shared/` (the contract), never
            redefined. Pick the transport(s) you need:

            | Subdir | Style | Use it for |
            |--------|-------|-----------|
            | `rest_fastapi/` | REST + auto OpenAPI (FastAPI/ASGI) | browser/3rd-party HTTP clients; self-documenting JSON API |
            | `grpc/` | gRPC (HTTP/2 + protobuf) | low-latency service-to-service, streaming, strict schemas |
            | `edge_nginx/` | HTTP/HTTPS reverse proxy | TLS termination + HTTP->HTTPS in front of the app |

            REST *is* the RESTful example (FastAPI generates the OpenAPI doc).
            For others not scaffolded — GraphQL, WebSockets, message queues —
            add a sibling subdir following the same thin-over-`src/` rule.
            `edge_nginx/` is edge **config**, not app code; in production it
            often lives in `ops/`.
            """,
            rules=[
                "Every transport is a thin adapter over `src/`; no domain logic "
                "in routes/handlers/servicers.",
                "HTTP DTOs / proto messages MIRROR `src/shared/`; keep one source "
                "of truth, don't redefine the contract per transport.",
                "Treat the OpenAPI doc and the `.proto` as contracts: keep them "
                "checked in and in sync; version them; don't break clients silently.",
                "`edge_nginx/` holds edge config only (TLS, proxy) — no app logic; "
                "never commit real certs/keys.",
            ]),
        "wiki": dict(
            kind="wiki",
            summary="(Optional) browsable knowledge/index site over the repo.",
            body="""
            Optional. A generated, browsable view of the code/docs (index,
            search, symbol tree). It is a *view*, never a source of truth —
            regenerate it from `src/`/`docs/`. Delete this dir if unused.
            """,
            rules=[
                "This is a generated view; never hand-edit content that should "
                "come from `src/`/`docs/`.",
                "Regenerate via its indexer; don't let it drift into a second "
                "source of truth.",
            ]),
        "scripts": dict(
            kind="script",
            summary="Dev and CI automation, one-shots, and this scaffold.",
            body="""
            Executable helpers, not importable library code. `scaffold.py` here
            (re)generates the skeleton. Anything reused by the app belongs in
            `src/`, not here.
            """,
            rules=[
                "Scripts are entrypoints, not libraries — if `src/` needs it, it "
                "moves to `src/`.",
                "Each script is self-describing (`--help`) and safe to run twice.",
            ]),
        "config": dict(
            kind="config",
            summary="Committed configuration defaults and examples (no secrets).",
            body="""
            Commit runtime defaults (`default.*`, `*.example.*`) and committed governance
            manifests (`project.json`, generated `*.schema.json`) — never secrets, which
            live in `*.local.*` or `.env` (gitignored). The `app/` layer loads runtime
            values from here; the checker reads the manifests (CONVENTIONS §15).
            """,
            rules=[
                "Never commit secrets — only defaults and `*.example.*`.",
                "Config is data, not code; the `app/` layer reads it, the "
                "domain layers receive values via injection.",
            ]),
        "demo": dict(
            kind="demo",
            summary="Runnable demos / examples of the system in use.",
            body="""
            Self-contained, runnable examples (`make demo`). They exercise the
            public API the way a user would — keep them honest, not mocked.
            """,
            rules=[
                "Demos use the public API only, like a real consumer.",
                "Keep demos runnable and current; a broken demo is a bug.",
            ]),
        "containers": dict(
            kind="container",
            summary="Dockerfiles, compose files, and image build context.",
            body="""
            Container/image definitions. Keep build context minimal; the image
            installs the package from the repo root. One subdir per image if you
            have several.
            """,
            rules=[
                "Images install the package; don't copy source ad-hoc.",
                "Pin base images; keep build context small.",
            ]),
        "evals": dict(
            kind="eval",
            summary="Evaluation suites for agents/models (not unit tests).",
            body="""
            Datasets + harness that score agent/model quality (accuracy,
            regressions, A/Bs). Distinct from `tests/`: evals measure quality on
            a distribution, tests assert correctness on cases.
            """,
            rules=[
                "Evals score quality on a dataset; they are not pass/fail unit "
                "tests — keep them out of `tests/`.",
                "Version datasets and record metrics over time.",
            ]),
        "ops": dict(
            kind="ops",
            summary="Deploy, IaC, runbooks, dashboards, observability.",
            body="""
            How the system is deployed and operated: IaC, deploy scripts,
            runbooks, alert/dashboard definitions. No application code.
            """,
            rules=[
                "Infra and runbooks only — no app logic.",
                "Runbooks are kept current with reality; stale runbooks are "
                "incidents waiting to happen.",
            ]),
        "models": dict(
            kind="model",
            summary="Model backends the app/agents run on — adapters + registry behind one contract.",
            body="""
            The catalog of **model backends** the system can run on. An agent is
            reasoning/policy; it needs a *model* to actually run — this is where
            those models live and how each is launched.

            | Path | Role |
            |------|------|
            | `__init__.py` | public API — `get_model(name=None)` returns a backend |
            | `contracts.py` | the `ModelBackend` ABC every adapter implements |
            | `registry.py` | name -> adapter + the default model |
            | `claude_code_headless.py` | adapter that runs Claude Code headless |
            | `config/` | per-model config (default model name, launch flags) |

            `agents/` depend on this dir: an agent asks the registry for a
            backend by name and calls `.run(prompt)`. To add a provider (an
            Anthropic API client, a local model), drop in an adapter that
            implements `ModelBackend` and register it — no agent code changes.
            """,
            rules=[
                "Every adapter implements the `ModelBackend` contract; callers "
                "depend on the contract, never on a concrete provider.",
                "Selecting/adding a model is a `registry.py` change — agents "
                "pick a model by name, never hardcode a provider or launch flag.",
                "Read secrets (API keys) from the environment, never from "
                "`config/` here.",
            ]),
        "runtimes": dict(
            kind="package",
            summary="Execute an agent's control flow as a neutral Plan — engines (in-process, LangGraph) are adapters behind one contract.",
            body="""
            An agent's *policy* is what it decides; its *control flow* is the
            order its steps run in. This package keeps control flow a **neutral
            concept** — a `Plan` (a flowchart of typed `Step`s + `Edge`s)
            executed by a `Runtime` — so the engine is one interchangeable
            adapter, exactly like `models/` for providers.

            | Path | Role |
            |------|------|
            | `__init__.py` | public API — `Plan`/`Step`/`Edge` + `get_runtime(name=None)` |
            | `contracts.py` | the `Plan` IR (Step/Edge/RunResult) and the `Runtime` ABC |
            | `registry.py` | name -> engine + the default (`inprocess`) |
            | `_inprocess.py` | the default **zero-dependency** engine (reference semantics) |
            | `langgraph_adapter.py` | one engine adapter — compiles a Plan to a LangGraph `StateGraph` |

            A `Step.effect` (`read-only`/`writes`/`model-call`) is its tool's
            effect (§10); a `writes`/`model-call` step is skipped unless the run
            is authorized (`execute=True`) — the dry-run guard lives here, once.
            LangGraph is one adapter, registered lazily and shipped as an
            optional extra; the default path imports nothing. See CONVENTIONS §16.
            """,
            rules=[
                "Every engine implements the `Runtime` contract; agents pick an "
                "engine by name via `get_runtime`, never import a concrete engine.",
                "An engine adapter changes **execution, never semantics**: the "
                "dry-run effect-guard and edge order must match the `inprocess` "
                "reference (pinned by tests/unit/runtimes/test_runtime_equivalence.py).",
                "A vendor/engine name (e.g. `langgraph`) appears **only inside "
                "its one adapter file** and its lazy registry thunk — never in "
                "`contracts.py`, the default engine, or in `agents/`.",
                "A new engine's dependency is an **optional extra** in "
                "`pyproject.toml`, imported lazily — the default install stays "
                "dependency-free.",
            ]),
    }
    layer_of = {"agents": "backend", "mcp": "backend", "api": "backend",
                "models": "backend", "runtimes": "backend"}
    for name, s in specs.items():
        readme(name, title=name.title() if name != "mcp" else "MCP",
               kind=s["kind"], layer=layer_of.get(name, "n/a"),
               summary=s["summary"], body=s["body"])
        claude(name, title=name, layer=layer_of.get(name, "n/a"),
               rules=s["rules"])

    # a couple of concrete placeholder files so dirs aren't bare
    w("config/default.example.toml", "# Committed example config. Copy to default.local.toml and edit.\n[app]\nname = \"project_keel\"\nlog_level = \"info\"\n")
    # Worked example: one collated, tunable surface for a RAG app. Runtime,
    # app-wide, language-neutral knobs live here (CONVENTIONS §8). The embedding/
    # reranker *adapter* choice lives in models/config/; secrets live in .env.
    w("config/rag.example.toml", textwrap.dedent("""
        # RAG knobs — copy to rag.local.toml and tune. NO secrets here (use .env).
        [retrieval]
        top_k = 8
        reranker = "bge-reranker-v2-m3"   # adapter selected in models/config/
        max_context_tokens = 8192

        [embedding]
        model = "text-embedding-3-large"  # adapter selected in models/config/
        dimensions = 1024
        batch_size = 64

        [chunking]
        chunk_tokens = 512
        overlap_tokens = 64

        [service]
        host = "0.0.0.0"
        port = 8000                        # the container/app reads this, not a copy
        request_timeout_s = 30
        """).strip() + "\n")
    # Machine-checked manifest of project facts (CONVENTIONS §15). JSON, not
    # TOML, so check_structure.py reads it under the old pre-commit python (no
    # tomllib). A committed decision, like the generated agent-surface schema.
    w("config/project.json", '''{
  "_comment": "Authoritative project facts: hand-edited, enforced by scripts/check_structure.py (check_H, CONVENTIONS section 15). Choose one frontend stack; list shipped stacks/transports under 'available'.",
  "name": "project_keel",
  "layers": {
    "frontend": {
      "stack": null,
      "language": "typescript",
      "root": "src/frontend",
      "available": ["react-vite", "astro"]
    },
    "backend": {
      "language": "python",
      "python": ">=3.10",
      "path": "src/backend"
    }
  },
  "transports": {
    "enabled": ["rest", "mcp"],
    "available": {
      "rest": "api/rest_fastapi",
      "grpc": "api/grpc",
      "edge_nginx": "api/edge_nginx",
      "mcp": "mcp"
    }
  },
  "runtimes": {
    "default": "inprocess",
    "available": {
      "inprocess": "runtimes",
      "langgraph": "runtimes"
    }
  }
}
''')
    w("scripts/README_scaffold.md", fm(
        title="scaffold.py", kind="script", layer="n/a", status="template",
        owner="TBD", summary="Regenerates the skeleton.") +
      "\n# scaffold.py\n\n`python3 scripts/scaffold.py [TARGET_DIR]` regenerates "
      "README/CLAUDE/convention docs and exemplar code. Safe to re-run.\n")
    w("demo/run_demo.py", textwrap.dedent('''
        """
        title: Demo runner
        kind: demo
        layer: n/a
        summary: Runs the public API like a user would.
        """
        import os
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from backend import do_thing

        if __name__ == "__main__":
            print(do_thing("demo", 42))
        ''').strip() + "\n")
    w("models/__init__.py", textwrap.dedent('''
        """
        title: Models public API
        layer: backend
        public_api: yes
        summary: get_model(name) -> a ModelBackend the agents/app run on.
        """
        from .contracts import ModelBackend
        from .registry import get_model, list_models

        __all__ = ["ModelBackend", "get_model", "list_models"]
        ''').strip() + "\n")
    w("models/contracts.py", textwrap.dedent('''
        """
        title: Model backend contract
        layer: backend
        public_api: yes
        summary: The ABC every model adapter implements.
        """
        from __future__ import annotations
        from abc import ABC, abstractmethod

        __all__ = ["ModelBackend"]


        class ModelBackend(ABC):
            """A runnable model. Agents depend on THIS, not on a provider."""

            name: str

            @abstractmethod
            def run(self, prompt: str, **opts) -> str:
                """Run the prompt on the model and return the text response."""
                raise NotImplementedError
        ''').strip() + "\n")
    w("models/claude_code_headless.py", textwrap.dedent('''
        """
        title: Claude Code headless backend
        layer: backend
        public_api: no
        summary: Runs a prompt via the Claude Code CLI in headless mode.
        """
        from __future__ import annotations
        import subprocess

        from .contracts import ModelBackend

        __all__ = ["ClaudeCodeHeadless"]


        class ClaudeCodeHeadless(ModelBackend):
            """Adapter that shells out to `claude -p` (headless, non-interactive).

            Replace flags/parsing to match your installed Claude Code version.
            API keys come from the environment, never from config files.
            """

            name = "claude-code-headless"

            def __init__(self, model: str = "claude-opus-4-8", binary: str = "claude"):
                self.model = model
                self.binary = binary

            def run(self, prompt: str, **opts) -> str:
                cmd = [self.binary, "-p", prompt, "--model", self.model]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    raise RuntimeError(f"claude headless failed: {proc.stderr.strip()}")
                return proc.stdout.strip()
        ''').strip() + "\n")
    w("models/registry.py", textwrap.dedent('''
        """
        title: Model registry
        layer: backend
        public_api: yes
        summary: name -> backend, plus the default. Add a provider here.
        """
        from __future__ import annotations

        from .claude_code_headless import ClaudeCodeHeadless
        from .contracts import ModelBackend

        __all__ = ["get_model", "list_models", "DEFAULT_MODEL"]

        DEFAULT_MODEL = "claude-code-headless"

        # name -> factory. To add a provider (Anthropic API client, local model),
        # write an adapter implementing ModelBackend and register it here.
        _REGISTRY = {
            "claude-code-headless": ClaudeCodeHeadless,
        }


        def list_models() -> list[str]:
            """Return the registered model names, sorted."""
            return sorted(_REGISTRY)


        def get_model(name: str | None = None, **kwargs) -> ModelBackend:
            """Return a model backend by name (defaults to DEFAULT_MODEL)."""
            key = name or DEFAULT_MODEL
            if key not in _REGISTRY:
                raise KeyError(f"unknown model {key!r}; have {list_models()}")
            return _REGISTRY[key](**kwargs)
        ''').strip() + "\n")
    w("models/config/default.example.toml",
      "# Per-model defaults. Copy to default.local.toml. NO secrets here.\n"
      "default_model = \"claude-code-headless\"\n\n"
      "[claude-code-headless]\n"
      "model = \"claude-opus-4-8\"\n"
      "binary = \"claude\"\n")
    # runtimes/ — agent control flow as a neutral Plan + Runtime (CONVENTIONS §16).
    # Embedded via the guarded _SRC mechanism so check_scaffold_sync keeps them
    # byte-identical to the live package (README/AGENT come from the specs loop).
    w("runtimes/__init__.py", _RT_INIT_SRC)
    w("runtimes/contracts.py", _RT_CONTRACTS_SRC)
    w("runtimes/_checkpoint.py", _RT_CHECKPOINT_SRC)
    w("runtimes/_inprocess.py", _RT_INPROCESS_SRC)
    w("runtimes/registry.py", _RT_REGISTRY_SRC)
    w("runtimes/langgraph_adapter.py", _RT_LANGGRAPH_SRC)
    w("tests/unit/runtimes/test_inprocess.py", _RT_TEST_INPROCESS_SRC)
    w("tests/unit/runtimes/test_runtime_equivalence.py", _RT_TEST_EQUIV_SRC)
    w("evals/README_run.md", fm(
        title="Running evals", kind="eval", layer="n/a", status="template",
        owner="TBD", summary="How to run the eval harness.") +
      "\n# Running evals\n\nPut datasets in `datasets/` and the harness here. "
      "Evals score quality; they are not unit tests.\n")
    keep("evals/datasets")
    keep("ops")
    keep("containers")


# --------------------------------------------------------------------------- #
# api/ transport examples
# --------------------------------------------------------------------------- #
def api_examples():
    _api_rest_fastapi("api/rest_fastapi")
    _api_grpc("api/grpc")
    _api_edge_nginx("api/edge_nginx")


def _api_rest_fastapi(base):
    readme(base, title="API — REST (FastAPI)", kind="api", layer="backend",
           public_api=f"{base}/openapi.json",
           summary="Thin FastAPI REST transport; auto-generates the OpenAPI contract.",
           body="""
           A FastAPI app that exposes the domain over REST and auto-generates
           the OpenAPI document. Run: `pip install -r requirements.txt` then
           `uvicorn app:app --reload`; docs at `/docs`.

           - `app.py` — routes; each calls `backend.do_thing` (thin).
           - `schemas.py` — Pydantic HTTP DTOs that MIRROR `src/shared/`.
           - `openapi.json` — checked-in contract snapshot.
           - `export_openapi.py` — regenerates `openapi.json` from the app.
           - `aad/` — optional **agent-surface adapter**: exposes a neutral
             `AgentSurface` (`src/backend/agent_surface/`) as a discoverable agent over
             the AAD wire format (one dialect; see `docs/guides/agent-surface.md`).
           """)
    claude(base, title="api/rest_fastapi", layer="backend", rules=[
        "Routes are thin: validate -> call `src/` -> shape response. No domain "
        "logic in handlers.",
        "Pydantic schemas mirror `src/shared/`; regenerate `openapi.json` "
        "(`python export_openapi.py`) whenever routes change.",
        "Version the path/prefix; don't break published routes silently.",
    ])
    w(f"{base}/requirements.txt", "fastapi>=0.115\nuvicorn[standard]>=0.32\npydantic>=2.9\n")
    w(f"{base}/schemas.py", textwrap.dedent('''
        """
        title: REST API schemas
        layer: backend
        public_api: no
        summary: Pydantic HTTP DTOs. Mirror the src/shared contract — one source of truth.
        """
        from pydantic import BaseModel

        __all__ = ["ThingIn", "ThingOut"]


        class ThingIn(BaseModel):
            """Request body for creating a Thing (mirrors src/shared)."""
            name: str
            value: int = 0


        class ThingOut(BaseModel):
            """Response body for a created Thing (mirrors src/shared)."""
            name: str
            value: int
        ''').strip() + "\n")
    w(f"{base}/app.py", textwrap.dedent('''
        """
        title: REST API (FastAPI)
        layer: backend
        public_api: no
        summary: Thin FastAPI transport over the backend domain; auto OpenAPI.
        """
        from __future__ import annotations

        import sys
        from pathlib import Path

        from fastapi import FastAPI

        # Transport calls into the domain via the package public API. In an
        # installed project (`pip install -e .`) `backend` is importable and this
        # sys.path shim goes away.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
        from backend import do_thing  # noqa: E402

        from schemas import ThingIn, ThingOut  # noqa: E402

        app = FastAPI(title="Project Keel API", version="0.0.0")


        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}


        @app.post("/things", response_model=ThingOut)
        def create_thing(body: ThingIn) -> ThingOut:
            thing = do_thing(body.name, body.value)  # delegate to the domain
            return ThingOut(name=thing.name, value=thing.value)
        ''').strip() + "\n")
    w(f"{base}/export_openapi.py", textwrap.dedent('''
        """Dump the live OpenAPI schema to openapi.json (keep it checked-in & in sync)."""
        import json

        from app import app

        if __name__ == "__main__":
            with open("openapi.json", "w") as fh:
                json.dump(app.openapi(), fh, indent=2)
            print("wrote openapi.json")
        ''').strip() + "\n")
    w(f"{base}/openapi.json", textwrap.dedent('''
        {
          "openapi": "3.1.0",
          "info": { "title": "Project Keel API", "version": "0.0.0" },
          "paths": {
            "/health": {
              "get": {
                "summary": "Health",
                "operationId": "health_health_get",
                "responses": {
                  "200": {
                    "description": "Successful Response",
                    "content": { "application/json": { "schema": { "type": "object", "additionalProperties": { "type": "string" } } } }
                  }
                }
              }
            },
            "/things": {
              "post": {
                "summary": "Create Thing",
                "operationId": "create_thing_things_post",
                "requestBody": {
                  "required": true,
                  "content": { "application/json": { "schema": { "$ref": "#/components/schemas/ThingIn" } } }
                },
                "responses": {
                  "200": {
                    "description": "Successful Response",
                    "content": { "application/json": { "schema": { "$ref": "#/components/schemas/ThingOut" } } }
                  }
                }
              }
            }
          },
          "components": {
            "schemas": {
              "ThingIn": {
                "type": "object",
                "title": "ThingIn",
                "required": ["name"],
                "properties": {
                  "name": { "type": "string", "title": "Name" },
                  "value": { "type": "integer", "title": "Value", "default": 0 }
                }
              },
              "ThingOut": {
                "type": "object",
                "title": "ThingOut",
                "required": ["name", "value"],
                "properties": {
                  "name": { "type": "string", "title": "Name" },
                  "value": { "type": "integer", "title": "Value" }
                }
              }
            }
          }
        }
        ''').strip() + "\n")


def _api_grpc(base):
    readme(base, title="API — gRPC", kind="api", layer="backend",
           public_api=f"{base}/proto/thing.proto",
           summary="Thin gRPC transport (HTTP/2 + protobuf) over the backend domain.",
           body="""
           gRPC service over HTTP/2 with protobuf. The `.proto` is the contract;
           Python stubs are generated, not committed.

           ```bash
           pip install -r requirements.txt
           make gen          # generate thing_pb2*.py from proto/thing.proto
           python server.py  # serves on :50051
           ```

           - `proto/thing.proto` — service + messages (mirror `src/shared/`).
           - `server.py` — servicer; `CreateThing` calls `backend.do_thing` (thin).
           """)
    claude(base, title="api/grpc", layer="backend", rules=[
        "The `.proto` is the contract — edit it first, regenerate stubs "
        "(`make gen`), keep messages mirroring `src/shared/`.",
        "Servicers are thin: unpack request -> call `src/` -> pack response.",
        "Generated `*_pb2.py` are build artifacts — don't hand-edit; gitignore "
        "them or generate in CI.",
    ])
    w(f"{base}/requirements.txt", "grpcio>=1.68\ngrpcio-tools>=1.68\nprotobuf>=5.28\n")
    w(f"{base}/proto/thing.proto", textwrap.dedent('''
        syntax = "proto3";

        package thing.v1;

        // Mirrors the src/shared `Thing` contract — one source of truth.
        message Thing {
          string name = 1;
          int32 value = 2;
        }

        message CreateThingRequest {
          string name = 1;
          int32 value = 2;
        }

        service ThingService {
          rpc CreateThing(CreateThingRequest) returns (Thing);
        }
        ''').strip() + "\n")
    w(f"{base}/server.py", textwrap.dedent('''
        """
        title: gRPC API
        layer: backend
        public_api: no
        summary: Thin gRPC transport over the backend domain.
        """
        from __future__ import annotations

        import sys
        from concurrent import futures
        from pathlib import Path

        import grpc

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
        from backend import do_thing  # noqa: E402

        # Generated from proto/thing.proto via `make gen`.
        import thing_pb2  # noqa: E402
        import thing_pb2_grpc  # noqa: E402


        class ThingService(thing_pb2_grpc.ThingServiceServicer):
            def CreateThing(self, request, context):
                thing = do_thing(request.name, request.value)  # delegate to domain
                return thing_pb2.Thing(name=thing.name, value=thing.value)


        def serve(port: int = 50051) -> None:
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
            thing_pb2_grpc.add_ThingServiceServicer_to_server(ThingService(), server)
            server.add_insecure_port(f"[::]:{port}")
            server.start()
            print(f"gRPC serving on :{port}")
            server.wait_for_termination()


        if __name__ == "__main__":
            serve()
        ''').strip() + "\n")
    w(f"{base}/Makefile", textwrap.dedent('''
        .PHONY: gen
        gen: ## Generate Python stubs from the proto
        \tpython -m grpc_tools.protoc -I proto \\
        \t\t--python_out=. --grpc_python_out=. proto/thing.proto
        ''').strip() + "\n")


def _api_edge_nginx(base):
    readme(base, title="API — HTTP/HTTPS edge (nginx)", kind="api",
           layer="n/a", public_api="none",
           summary="Reverse proxy: TLS termination + HTTP->HTTPS in front of the app.",
           body="""
           The HTTP/HTTPS **edge** that sits in front of the transports above:
           terminates TLS, forces HTTP->HTTPS, and reverse-proxies to the
           FastAPI/uvicorn upstream. This is deployment **config**, not app code
           — in production it often lives in `ops/`. Real certs/keys are never
           committed (see the placeholder paths).

           - `nginx.conf` — HTTP->HTTPS redirect + TLS server + `proxy_pass`.
             A commented `grpc_pass` block shows the gRPC variant.
           """)
    claude(base, title="api/edge_nginx", layer="n/a", rules=[
        "Edge config only — TLS, redirects, proxy. No application logic.",
        "Never commit real certificates or private keys; reference paths only.",
        "Keep the upstream host/port in sync with how the app transport is run.",
    ])
    w(f"{base}/nginx.conf", textwrap.dedent('''
        # HTTP/HTTPS edge in front of the app transport (FastAPI/uvicorn or gRPC).
        # Terminates TLS, forces HTTPS, reverse-proxies to the upstream.

        upstream app {
            # uvicorn app:app --host 127.0.0.1 --port 8000
            server 127.0.0.1:8000;
        }

        # Redirect all plain HTTP to HTTPS.
        server {
            listen 80;
            server_name example.com;
            return 301 https://$host$request_uri;
        }

        # TLS termination + reverse proxy.
        server {
            listen 443 ssl;
            http2 on;
            server_name example.com;

            # Placeholders — provision real certs out of band; NEVER commit them.
            ssl_certificate     /etc/ssl/certs/example.com.crt;
            ssl_certificate_key /etc/ssl/private/example.com.key;

            add_header Strict-Transport-Security "max-age=63072000" always;
            add_header X-Content-Type-Options nosniff always;

            location / {
                proxy_pass http://app;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
            }

            # gRPC variant: proxy to a grpc upstream instead.
            # location / {
            #     grpc_pass grpc://127.0.0.1:50051;
            # }
        }
        ''').strip() + "\n")


# --------------------------------------------------------------------------- #
# quality tooling — the conventions validator + pre-commit
# --------------------------------------------------------------------------- #
def quality_tooling():
    w("scripts/check_structure.py", _CHECK_STRUCTURE_SRC)
    w("scripts/check_scaffold_sync.py", _CHECK_SCAFFOLD_SYNC_SRC)
    w("scripts/jobs/check_corpus.py", _CHECK_CORPUS_SRC)
    w("scripts/README_check_structure.md", fm(
        title="check_structure.py", kind="script", layer="n/a",
        status="template", owner="TBD",
        summary="Enforces the CONVENTIONS.md labeling + boundary rules.") +
      textwrap.dedent("""
        # check_structure.py

        Makes the conventions self-enforcing. `python3 scripts/check_structure.py`
        (or `make check`) fails with a non-zero exit if any of these drift:

        - **Frontmatter** — every `README.md`/`CLAUDE.md` (and `docs/**`,
          `test-docs/**` markdown) has the required keys with valid
          `kind`/`layer`/`status` values.
        - **Documented dirs** — every taxonomy directory that exists carries
          both a `README.md` and a `CLAUDE.md`.
        - **Package boundary** — every `src/` dir with `.py` files has an
          `__init__.py` that defines `__all__`.
        - **`__init__` is the API** — no code does an absolute import of another
          package's `_private` module; callers go through the public API.

        Warnings (e.g. a missing `owner`) are printed but do not fail the build.
        Stdlib only; runs on Python 3.6+.
        """).strip() + "\n")
    w(".pre-commit-config.yaml", textwrap.dedent("""
        # Install once:  pip install pre-commit && pre-commit install
        # Each hook below is a thin TRIGGER (an adapter) that fires a doer;
        # the doer's logic lives in scripts/ or the tool, never inline here.
        repos:
          - repo: local
            hooks:
              - id: structure
                name: structure & frontmatter conventions
                entry: python3 scripts/check_structure.py
                language: system
                pass_filenames: false
                always_run: true
              - id: eslint
                name: eslint (frontend)
                entry: make lint-fe
                language: system
                pass_filenames: false
                files: \\.(ts|tsx|js|jsx|astro)$
              - id: cdmon
                name: cdmon code-doc drift (no-op if cdmon not installed)
                entry: python3 scripts/cdmon_sync.py --check
                language: system
                pass_filenames: false
                always_run: true
              - id: aad-schema
                name: AAD schema in sync with the model (skips if pydantic absent)
                entry: python3 scripts/agent_surface/generate_aad_schema.py --check
                language: system
                pass_filenames: false
                always_run: true
              - id: scaffold-sync
                name: scaffold.py embeds match the live scripts
                entry: python3 scripts/check_scaffold_sync.py --check
                language: system
                pass_filenames: false
                always_run: true
              - id: openapi
                name: openapi.json in sync with the app (skips if FastAPI absent)
                entry: python3 api/rest_fastapi/export_openapi.py --check
                language: system
                pass_filenames: false
                always_run: true
          - repo: https://github.com/astral-sh/ruff-pre-commit
            rev: v0.8.4
            hooks:
              - id: ruff
              - id: ruff-format
        """).strip() + "\n")


# runtimes/ package sources (CONVENTIONS §16). Placeholders here; kept
# byte-identical to the live files by check_scaffold_sync --write (the same
# guarded _SRC mechanism as the check scripts). Run that after editing runtimes/.
_RT_CHECKPOINT_SRC = r'''"""
title: Checkpointer implementations
layer: backend
public_api: no
summary: In-memory and JSON-file Checkpointer backends for durable/ resumable runs.
"""
from __future__ import annotations

import copy
import json
import os
from typing import Optional

from .contracts import Checkpointer

__all__ = ["MemoryCheckpointer", "FileCheckpointer"]


class MemoryCheckpointer(Checkpointer):
    """Process-local checkpointer: keeps snapshots in a dict (deep-copied).

    Good for tests and single-process pauses. Holds arbitrary Python state (no
    JSON constraint), but does not survive process exit -- use FileCheckpointer
    for crash recovery across processes.
    """

    def __init__(self):
        self._store = {}

    def save(self, key, snapshot):
        """Store a deep copy of ``snapshot`` so later state mutation can't bleed in."""
        self._store[key] = copy.deepcopy(snapshot)

    def load(self, key):
        """Return a deep copy of the snapshot under ``key`` (or None)."""
        snap = self._store.get(key)
        return copy.deepcopy(snap) if snap is not None else None

    def clear(self, key):
        """Drop the snapshot under ``key`` if present."""
        self._store.pop(key, None)


class FileCheckpointer(Checkpointer):
    """JSON-file checkpointer for cross-process crash recovery.

    Each ``key`` is a ``<key>.json`` file under a directory. State must be
    JSON-serialisable (the price of surviving a process exit). Writes are atomic
    (temp file + rename) so a crash mid-write can't corrupt the snapshot.
    """

    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, key):
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in key)
        return os.path.join(self.directory, safe + ".json")

    def save(self, key, snapshot):
        """Atomically write ``snapshot`` as JSON (temp file + os.replace)."""
        path = self._path(key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, sort_keys=True)
        os.replace(tmp, path)

    def load(self, key) -> Optional[dict]:
        """Return the JSON snapshot under ``key``, or None if absent."""
        path = self._path(key)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def clear(self, key):
        """Remove the snapshot file under ``key`` if present."""
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
'''
_RT_INIT_SRC = r'''"""
title: Runtimes public API
layer: backend
summary: Build a Plan (Step/Edge flowchart) and get_runtime(name) to execute it — with durability, human-in-the-loop, fan-out, and streaming.
"""
from ._checkpoint import FileCheckpointer, MemoryCheckpointer
from .contracts import (
    COMPLETED,
    EFFECTS,
    END,
    MODEL_CALL,
    PAUSED,
    READ_ONLY,
    WRITES,
    Checkpointer,
    Edge,
    Pause,
    Plan,
    RunResult,
    Runtime,
    Step,
    TraceEntry,
    interrupt,
)
from .registry import DEFAULT_RUNTIME, get_runtime, list_runtimes

__all__ = [
    "READ_ONLY", "WRITES", "MODEL_CALL", "EFFECTS", "END",
    "COMPLETED", "PAUSED",
    "Step", "Edge", "Plan", "TraceEntry", "RunResult", "Runtime",
    "Checkpointer", "MemoryCheckpointer", "FileCheckpointer",
    "Pause", "interrupt",
    "get_runtime", "list_runtimes", "DEFAULT_RUNTIME",
]
'''
_RT_CONTRACTS_SRC = r'''"""
title: Agent runtime contract
layer: backend
public_api: yes
summary: The neutral Plan/Step/Edge flowchart IR, the Runtime ABC, and the durability/HIL/fan-out capabilities every engine implements.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

__all__ = [
    "READ_ONLY", "WRITES", "MODEL_CALL", "EFFECTS", "END",
    "COMPLETED", "PAUSED",
    "Step", "Edge", "Plan", "TraceEntry", "RunResult", "Runtime",
    "Checkpointer", "Pause", "interrupt",
]

# Effect vocabulary -- identical to the `tool_effect` set in CONVENTIONS section
# 10, so a Step's effect IS its tool's declared effect. The runtime treats
# WRITES and MODEL_CALL as side-effecting: such a step is a no-op (never called)
# unless the run is authorized with execute=True. READ_ONLY steps always run.
# These same effectful steps are the natural durability commit points (a crash
# after them would lose real work); see Checkpointer.
READ_ONLY = "read-only"
WRITES = "writes"
MODEL_CALL = "model-call"
EFFECTS = (READ_ONLY, WRITES, MODEL_CALL)

# Neutral terminal sentinel: an edge to END ends the run. Mirrors LangGraph's
# END marker without importing it, so the IR names no vendor.
END = "__end__"

# RunResult.status values.
COMPLETED = "completed"
PAUSED = "paused"


@dataclass(frozen=True)
class Step:
    """One node in a plan: a named unit of work with a declared side-effect.

    ``run(state)`` returns a dict merged into the run state (or ``None`` for no
    change). ``effect`` is one of EFFECTS; a ``writes``/``model-call`` step is
    skipped -- its ``run`` is never invoked -- unless the run is authorized
    (``execute=True``).

    ``fan_out`` makes this a **map** step: when set, ``fan_out(state)`` returns a
    list of items and ``run`` is invoked once per item with ``state["item"]`` (and
    ``state["index"]``) bound; the per-item results are collected, in item order,
    under ``state[name]``. The default engine runs them sequentially; the
    LangGraph engine fans them out concurrently -- same ordered result either way.
    """

    name: str
    effect: str
    run: Callable[[dict], Optional[dict]]
    fan_out: Optional[Callable[[dict], list]] = None


@dataclass(frozen=True)
class Edge:
    """A directed transition ``src -> dst``, taken when ``when(state)`` is true.

    ``when=None`` is an unconditional edge. A runtime evaluates a node's
    outgoing edges in declaration order and follows the first whose ``when`` is
    ``None`` or returns true; ``dst == END`` ends the run. Branch predicates are
    pure functions of state -- this is what keeps control flow deterministic.
    An edge whose ``dst`` is an earlier node forms a cycle (e.g. iterative RAG).
    """

    src: str
    dst: str
    when: Optional[Callable[[dict], bool]] = None


@dataclass(frozen=True)
class Plan:
    """An agent's control flow as inspectable data: a flowchart of Steps.

    ``entry`` names the first step; ``steps`` are the nodes; ``edges`` are the
    transitions. The same Plan runs identically on any Runtime -- the engine
    changes how it executes, never what it means.
    """

    name: str
    entry: str
    steps: Tuple[Step, ...]
    edges: Tuple[Edge, ...]

    def step(self, name: str) -> Step:
        """Return the Step with this name, or raise KeyError if absent."""
        for s in self.steps:
            if s.name == name:
                return s
        raise KeyError(name)

    def next_from(self, current: str, state: dict) -> str:
        """Return the dst of the first matching outgoing edge from ``current``.

        Edges are tried in declaration order; the first whose ``when`` is None or
        returns true wins, else END. This is the single definition of edge
        semantics both engines share, so routing can't drift between them.
        """
        for edge in self.edges:
            if edge.src == current and (edge.when is None or edge.when(state)):
                return edge.dst
        return END

    def to_mermaid(self) -> str:
        """Render the plan as a Mermaid ``flowchart`` (it is already a graph).

        Nodes show their effect; a fan-out step is marked; conditional edges are
        dashed. Useful for docs/review and as the neutral analogue of LangGraph
        Studio -- no engine or vendor needed to visualise the flow.
        """
        shape = {READ_ONLY: ('["', '"]'), WRITES: ('[/"', '"/]'),
                 MODEL_CALL: ('{{"', '"}}')}
        lines = ["flowchart TD"]
        for s in self.steps:
            lo, hi = shape.get(s.effect, ('["', '"]'))
            tag = " &laquo;map&raquo;" if s.fan_out else ""
            lines.append("    %s%s%s (%s)%s%s" % (s.name, lo, s.name, s.effect, tag, hi))
        lines.append('    %s(("END"))' % "_END")
        for e in self.edges:
            dst = "_END" if e.dst == END else e.dst
            arrow = "-.->" if e.when is not None else "-->"
            lines.append("    %s %s %s" % (e.src, arrow, dst))
        return "\n".join(lines)


@dataclass(frozen=True)
class TraceEntry:
    """One executed (or skipped) node, in execution order -- the run's audit trail."""

    step: str
    effect: str
    ran: bool             # False => skipped (gated step in a dry run)
    skipped_reason: str   # "" when ran; else "dry-run"


@dataclass(frozen=True)
class RunResult:
    """The final run state, the ordered trace, and the run's terminal status.

    ``status`` is ``completed`` or ``paused``; when paused, ``interrupt`` carries
    the payload a step surfaced for a human, and the run can be resumed via
    ``Runtime.run(..., checkpointer=..., run_key=..., resume=<value>)``.
    """

    state: dict
    trace: Tuple[TraceEntry, ...]
    status: str = COMPLETED
    interrupt: object = None


class Runtime(ABC):
    """Executes a Plan. Engines (in-process, LangGraph, ...) are adapters of this.

    Callers depend on THIS, never on a concrete engine. An adapter changes HOW a
    plan executes (eager walk, compiled graph, durable checkpoints, fan-out) but
    never WHAT it means: the dry-run effect-guard, edge semantics, durability,
    human-in-the-loop, and fan-out ordering are identical across runtimes, pinned
    by ``tests/unit/runtimes/test_runtime_equivalence.py``.
    """

    name: str

    @abstractmethod
    def run(self, plan: Plan, state: Optional[dict] = None, *,
            execute: bool = False, checkpointer: "Optional[Checkpointer]" = None,
            run_key: str = "run", resume: object = ..., on_event=None) -> RunResult:
        """Execute ``plan`` from its entry node (or resume) and return a RunResult.

        ``execute`` authorises side-effecting (``writes``/``model-call``) steps.
        ``checkpointer`` (with ``run_key``) makes the run **durable**: state is
        snapshotted at step boundaries so it can resume after a crash or a pause.
        ``resume`` (anything other than the default sentinel) resumes a suspended
        run, injecting the value into the paused step's ``interrupt`` call.
        ``on_event`` is called once per step for **streaming** progress.
        """
        raise NotImplementedError


class Checkpointer(ABC):
    """Persists a run snapshot so a plan can resume after a crash or a pause.

    A snapshot is a plain dict (``cursor`` + ``state`` + ``trace``); the default
    engine writes one at each step boundary. Durability is keyed by ``run_key``,
    so concurrent runs don't collide. Implementations: an in-memory store for
    tests, a JSON file for cross-process recovery (see ``runtimes._checkpoint``).
    """

    @abstractmethod
    def save(self, key: str, snapshot: dict) -> None:
        """Persist ``snapshot`` under ``key`` (overwriting any prior one)."""
        raise NotImplementedError

    @abstractmethod
    def load(self, key: str) -> Optional[dict]:
        """Return the snapshot saved under ``key``, or ``None`` if there is none."""
        raise NotImplementedError

    @abstractmethod
    def clear(self, key: str) -> None:
        """Drop the snapshot under ``key`` (called when a run completes)."""
        raise NotImplementedError


class Pause(Exception):
    """Raised by ``interrupt`` to suspend a run pending human input.

    Engines catch this, checkpoint, and return a ``paused`` RunResult carrying
    the payload. Callers never raise it directly -- they call ``interrupt``.
    """

    def __init__(self, payload=None):
        super().__init__("paused")
        self.payload = payload


def interrupt(state: dict, payload=None):
    """Request human input from within a step (human-in-the-loop).

    On the first encounter the run **suspends**: the caller receives a ``paused``
    RunResult whose ``interrupt`` is ``payload``. When the run is resumed with a
    value, this call **returns that value** so the step proceeds. The engine
    injects the actual mechanism under ``state["_interrupt"]`` so this stays
    vendor-neutral; calling it outside a run raises RuntimeError.
    """
    impl = state.get("_interrupt")
    if impl is None:
        raise RuntimeError("interrupt() called outside a runtime run")
    return impl(payload)
'''
_RT_INPROCESS_SRC = r'''"""
title: In-process runtime
layer: backend
public_api: no
summary: The default zero-dependency Plan executor; reference semantics for the dry-run guard, durability, HIL, fan-out, and streaming.
"""
from __future__ import annotations

from .contracts import (
    COMPLETED,
    END,
    MODEL_CALL,
    PAUSED,
    WRITES,
    Pause,
    RunResult,
    Runtime,
    TraceEntry,
)

__all__ = ["InProcessRuntime"]

_GATED = (WRITES, MODEL_CALL)
_MAX_STEPS = 10000
_UNSET = object()
_INTERNAL = ("_interrupt",)   # engine-injected keys never returned to the caller


def _public(state):
    """Return state without engine-internal keys (e.g. the interrupt hook)."""
    return {k: v for k, v in state.items() if k not in _INTERNAL}


def _rows(trace):
    return [[t.step, t.effect, t.ran, t.skipped_reason] for t in trace]


def _objs(rows):
    return [TraceEntry(*r) for r in rows]


def _run_step(step, state):
    """Run a Step. A fan-out step runs its body per item (in order) and collects
    the per-item results, in item order, under ``state[step.name]``."""
    if step.fan_out is None:
        return step.run(state)
    results = []
    for index, item in enumerate(step.fan_out(state)):
        sub = dict(state)
        sub["item"] = item
        sub["index"] = index
        results.append(step.run(sub))
    return {step.name: results}


class InProcessRuntime(Runtime):
    """Walk a Plan's edges in pure Python -- no dependencies, runs anywhere.

    This is the DEFAULT runtime and the *reference semantics* every other engine
    must match: a ``writes``/``model-call`` step is skipped unless
    ``execute=True``; the first matching outgoing edge is followed until END;
    a ``checkpointer`` snapshots state at each step boundary (durable resume);
    ``interrupt`` suspends for human input; ``fan_out`` maps a step over items;
    ``on_event`` streams per-step progress. Pure stdlib -- runs under CI,
    pre-commit, and the app with no install.
    """

    name = "inprocess"

    def run(self, plan, state=None, *, execute=False, checkpointer=None,
            run_key="run", resume=_UNSET, on_event=None):
        """Execute (or resume) the plan; return final state, trace, and status."""
        resume_box = {"has": resume is not _UNSET, "value": resume}
        if resume is not _UNSET:
            if checkpointer is None:
                raise RuntimeError("resume requires a checkpointer")
            snap = checkpointer.load(run_key)
            if snap is None:
                raise RuntimeError("no checkpoint to resume for run_key %r" % run_key)
            st = dict(snap["state"])
            trace = _objs(snap["trace"])
            current = snap["cursor"]
        else:
            st = dict(state or {})
            trace = []
            current = plan.entry

        def _interrupt(payload):
            if resume_box["has"]:
                resume_box["has"] = False
                return resume_box["value"]
            raise Pause(payload)
        st["_interrupt"] = _interrupt

        steps = 0
        while current and current != END:
            step = plan.step(current)
            if step.effect in _GATED and not execute:
                trace.append(TraceEntry(step.name, step.effect, False, "dry-run"))
                self._emit(on_event, step.name, step.effect, False, "dry-run")
            else:
                try:
                    update = _run_step(step, st)
                except Pause as p:
                    if checkpointer is not None:
                        checkpointer.save(run_key, {"cursor": current,
                                                    "state": _public(st),
                                                    "trace": _rows(trace)})
                    return RunResult(state=_public(st), trace=tuple(trace),
                                     status=PAUSED, interrupt=p.payload)
                if update:
                    st.update(update)
                trace.append(TraceEntry(step.name, step.effect, True, ""))
                self._emit(on_event, step.name, step.effect, True, "")
            current = plan.next_from(current, st)
            # Durability commit point: snapshot after every step. The effect
            # taxonomy means we only strictly need this after writes/model-call
            # steps; snapshotting after read-only steps too is a harmless, simpler
            # over-approximation (a resume just skips re-running cheap steps).
            if checkpointer is not None and current != END:
                checkpointer.save(run_key, {"cursor": current,
                                            "state": _public(st),
                                            "trace": _rows(trace)})
            steps += 1
            if steps > _MAX_STEPS:
                raise RuntimeError(
                    "plan %r exceeded %d steps (cyclic plan with no exit?)"
                    % (plan.name, _MAX_STEPS))
        if checkpointer is not None:
            checkpointer.clear(run_key)
        return RunResult(state=_public(st), trace=tuple(trace), status=COMPLETED)

    @staticmethod
    def _emit(on_event, name, effect, ran, reason):
        if on_event is not None:
            on_event({"step": name, "effect": effect, "ran": ran,
                      "skipped_reason": reason})
'''
_RT_REGISTRY_SRC = r'''"""
title: Runtime registry
layer: backend
public_api: yes
summary: name -> runtime engine, plus the default. Add an engine adapter here.
"""
from __future__ import annotations

from ._inprocess import InProcessRuntime
from .contracts import Runtime

__all__ = ["get_runtime", "list_runtimes", "DEFAULT_RUNTIME"]

DEFAULT_RUNTIME = "inprocess"


def _load_langgraph():
    """Resolve the LangGraph engine lazily (import only when it is selected)."""
    from .langgraph_adapter import LangGraphRuntime
    return LangGraphRuntime


# name -> a thunk returning the engine class. The default is pure stdlib;
# 'langgraph' is LAZY so the default path (CI, pre-commit, the app) never
# imports langgraph or its dependency tree -- it is an optional extra
# (pyproject [project.optional-dependencies] langgraph). To add an engine, write
# an adapter implementing the Runtime contract and register its thunk here.
_REGISTRY = {
    "inprocess": lambda: InProcessRuntime,
    "langgraph": _load_langgraph,
}


def list_runtimes() -> list:
    """Return the registered runtime names, sorted (registered != installed)."""
    return sorted(_REGISTRY)


def get_runtime(name: str | None = None, **kwargs) -> Runtime:
    """Return a runtime engine by name (defaults to DEFAULT_RUNTIME).

    Raises KeyError for an unknown name; selecting an engine whose optional
    dependency is absent raises ImportError from its lazy loader (e.g.
    ``get_runtime("langgraph")`` without LangGraph installed).
    """
    key = name or DEFAULT_RUNTIME
    if key not in _REGISTRY:
        raise KeyError("unknown runtime %r; have %s" % (key, list_runtimes()))
    engine_cls = _REGISTRY[key]()
    return engine_cls(**kwargs)
'''
_RT_LANGGRAPH_SRC = r'''"""
title: LangGraph runtime adapter
layer: backend
public_api: no
summary: One engine adapter -- compiles a neutral Plan into a LangGraph StateGraph (durability, HIL, fan-out via Send, streaming).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Annotated, TypedDict

from .contracts import (
    COMPLETED,
    END,
    MODEL_CALL,
    PAUSED,
    WRITES,
    Pause,
    RunResult,
    Runtime,
    TraceEntry,
)

__all__ = ["LangGraphRuntime"]

_GATED = (WRITES, MODEL_CALL)
_UNSET = object()
_INTERNAL = ("_interrupt", "_execute", "_trace")


def _merge(old, new):
    """Reducer: accumulate the evolving plan state as one last-value-merged dict."""
    merged = dict(old or {})
    merged.update(new or {})
    return merged


def _concat(old, new):
    """Reducer: gather fan-out worker results (each concurrent worker appends)."""
    return list(old or []) + list(new or [])


# The evolving plan state rides one merge-reduced `bag` channel; `collect` is a
# concat-reduced channel where fan-out workers (LangGraph Send) drop their
# per-item results to be reassembled in order. Defined at module scope so
# get_type_hints resolves it despite `from __future__ import annotations`.
class _PlanState(TypedDict):
    bag: Annotated[dict, _merge]
    collect: Annotated[list, _concat]


class _PauseSignal(Exception):
    """Internal: abort a LangGraph invoke when a step pauses (details in holder)."""


def _public(bag):
    return {k: v for k, v in bag.items() if k not in _INTERNAL}


def _emit(on_event, name, effect, ran, reason):
    if on_event is not None:
        on_event({"step": name, "effect": effect, "ran": ran, "skipped_reason": reason})


class LangGraphRuntime(Runtime):
    """Execute a Plan on LangGraph -- the vendor name is confined to THIS file.

    Compiles each Step into a ``StateGraph`` node and each Edge into an
    ``add_edge`` / ``add_conditional_edges`` transition, applying the IDENTICAL
    dry-run guard, durability, human-in-the-loop, and edge order as the
    in-process reference, so it changes execution and never semantics. Fan-out
    steps dispatch concurrently via LangGraph's ``Send`` and are reassembled in
    item order; resume re-enters the graph at the checkpoint cursor.

    LangGraph is an optional dependency (``pip install -e '.[langgraph]'``)
    imported lazily here, so the default install and the pre-commit path pull
    nothing. Equivalence with the default engine is pinned by
    ``tests/unit/runtimes/test_runtime_equivalence.py``.
    """

    name = "langgraph"

    def run(self, plan, state=None, *, execute=False, checkpointer=None,
            run_key="run", resume=_UNSET, on_event=None):
        """Compile ``plan`` to a StateGraph, invoke (or resume) it, return a RunResult."""
        from langgraph.graph import StateGraph

        resume_box = {"has": resume is not _UNSET, "value": resume}
        if resume is not _UNSET:
            if checkpointer is None:
                raise RuntimeError("resume requires a checkpointer")
            snap = checkpointer.load(run_key)
            if snap is None:
                raise RuntimeError("no checkpoint to resume for run_key %r" % run_key)
            bag0 = dict(snap["state"])
            bag0["_trace"] = [list(r) for r in snap["trace"]]
            entry = snap["cursor"]
        else:
            bag0 = dict(state or {})
            bag0["_trace"] = []
            entry = plan.entry
        bag0["_execute"] = execute

        holder = {}
        builder = StateGraph(_PlanState)
        for step in plan.steps:
            if step.fan_out is None:
                builder.add_node(step.name, self._node(
                    plan, step, checkpointer, run_key, on_event, resume_box, holder))
            else:
                self._add_fan_out(builder, plan, step, checkpointer, run_key, on_event)
        builder.set_entry_point(entry)
        _wire(builder, plan)
        graph = builder.compile()

        try:
            final = graph.invoke({"bag": bag0, "collect": []})
        except Exception:
            if not holder.get("paused"):
                raise
            if checkpointer is not None:
                checkpointer.save(run_key, {"cursor": holder["cursor"],
                                            "state": holder["state"],
                                            "trace": holder["trace"]})
            return RunResult(state=holder["state"],
                             trace=tuple(TraceEntry(*r) for r in holder["trace"]),
                             status=PAUSED, interrupt=holder["payload"])

        bag = final["bag"]
        if checkpointer is not None:
            checkpointer.clear(run_key)
        return RunResult(state=_public(bag),
                         trace=tuple(TraceEntry(*r) for r in bag.get("_trace", [])),
                         status=COMPLETED)

    def _node(self, plan, step, checkpointer, run_key, on_event, resume_box, holder):
        """Wrap a normal Step as a LangGraph node (dry-run guard, HIL, checkpoint)."""
        def _interrupt(payload):
            if resume_box["has"]:
                resume_box["has"] = False
                return resume_box["value"]
            raise Pause(payload)

        def node(state):
            bag = state["bag"]
            execute = bag.get("_execute", False)
            trace = list(bag.get("_trace", []))
            if step.effect in _GATED and not execute:
                _emit(on_event, step.name, step.effect, False, "dry-run")
                return {"bag": {"_trace": trace + [[step.name, step.effect, False, "dry-run"]]}}
            local = dict(bag)
            local["_interrupt"] = _interrupt
            try:
                update = step.run(local) or {}
            except Pause as p:
                holder.update(paused=True, payload=p.payload, cursor=step.name,
                              state=_public(bag), trace=trace)
                raise _PauseSignal()
            new = dict(update)
            new["_trace"] = trace + [[step.name, step.effect, True, ""]]
            _emit(on_event, step.name, step.effect, True, "")
            _checkpoint_after(checkpointer, run_key, plan, step.name, bag, update, new["_trace"])
            return {"bag": new}
        return node

    @staticmethod
    def _add_fan_out(builder, plan, step, checkpointer, run_key, on_event):
        """Compile a fan-out Step into dispatch -> worker (Send) -> gather nodes."""
        from langgraph.types import Send

        worker_name = step.name + "__worker"
        gather_name = step.name + "__gather"

        def dispatch(state):
            return {}   # routing happens on the conditional edge below

        def route(state):
            bag = state["bag"]
            if step.effect in _GATED and not bag.get("_execute", False):
                return gather_name   # skipped: gather emits the skipped trace
            items = list(step.fan_out(bag))
            if not items:
                return gather_name
            sends = []
            for index, item in enumerate(items):
                payload = dict(bag)
                payload["item"] = item
                payload["index"] = index
                sends.append(Send(worker_name, {"bag": payload}))
            return sends

        def worker(state):
            bag = state["bag"]
            result = step.run(bag) or {}
            return {"collect": [[step.name, bag["index"], result]]}

        def gather(state):
            bag = state["bag"]
            execute = bag.get("_execute", False)
            trace = list(bag.get("_trace", []))
            if step.effect in _GATED and not execute:
                _emit(on_event, step.name, step.effect, False, "dry-run")
                return {"bag": {"_trace": trace + [[step.name, step.effect, False, "dry-run"]]}}
            mine = [(idx, res) for (nm, idx, res) in state.get("collect", [])
                    if nm == step.name]
            mine.sort(key=lambda pair: pair[0])
            update = {step.name: [res for _, res in mine]}
            new = dict(update)
            new["_trace"] = trace + [[step.name, step.effect, True, ""]]
            _emit(on_event, step.name, step.effect, True, "")
            _checkpoint_after(checkpointer, run_key, plan, step.name, bag, update, new["_trace"])
            return {"bag": new}

        builder.add_node(step.name, dispatch)
        builder.add_node(worker_name, worker)
        builder.add_node(gather_name, gather)
        builder.add_conditional_edges(
            step.name, route, {gather_name: gather_name, worker_name: worker_name})
        builder.add_edge(worker_name, gather_name)
        # gather_name -> the step's normal successors is wired by _wire (it
        # re-homes the plan edges whose src == step.name onto the gather node).


def _checkpoint_after(checkpointer, run_key, plan, name, bag, update, new_trace):
    """Durability commit point: snapshot after a step (cursor = the next node)."""
    if checkpointer is None:
        return
    post = dict(bag)
    post.update(update or {})
    nxt = plan.next_from(name, post)
    if nxt != END:
        checkpointer.save(run_key, {"cursor": nxt, "state": _public(post),
                                    "trace": new_trace})


def _wire(builder, plan):
    """Translate plan edges into LangGraph (conditional) edges, by source.

    A fan-out step's outgoing edges are re-homed onto its ``::gather`` node, so
    routing after the fan-out sees the collected results.
    """
    from langgraph.graph import END as LG_END

    fan_names = set(s.name for s in plan.steps if s.fan_out is not None)
    by_src = OrderedDict()
    for edge in plan.edges:
        src = edge.src + "__gather" if edge.src in fan_names else edge.src
        by_src.setdefault(src, []).append(edge)
    for src, edges in by_src.items():
        if len(edges) == 1 and edges[0].when is None:
            dst = edges[0].dst
            builder.add_edge(src, LG_END if dst == END else dst)
        else:
            builder.add_conditional_edges(src, _router(edges), _dest_map(edges, LG_END))


def _router(edges):
    """Return a path function mirroring 'first matching outgoing edge' order."""
    def route(state):
        bag = state["bag"]
        for edge in edges:
            if edge.when is None or edge.when(bag):
                return edge.dst
        return END
    return route


def _dest_map(edges, lg_end):
    """Map each possible router result (incl. END) to its LangGraph target."""
    dest = {}
    for edge in edges:
        dest[edge.dst] = lg_end if edge.dst == END else edge.dst
    dest[END] = lg_end   # fallback when no edge matched
    return dest
'''
_RT_TEST_INPROCESS_SRC = r'''"""
title: Unit — runtimes (default in-process engine + capabilities)
kind: tests
layer: backend
summary: Reference semantics — edge routing, dry-run guard, streaming, fan-out, durability, human-in-the-loop. No deps, no disk.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from runtimes import (  # noqa: E402
    COMPLETED,
    END,
    MODEL_CALL,
    PAUSED,
    READ_ONLY,
    WRITES,
    DEFAULT_RUNTIME,
    Edge,
    MemoryCheckpointer,
    Plan,
    Step,
    get_runtime,
    interrupt,
    list_runtimes,
)

pytestmark = pytest.mark.unit


def _rt():
    return get_runtime("inprocess")


def _branching_plan(calls):
    """gate -> build(writes) -> report -> fill(model) ; gate -> report when dirty."""
    def gate(s):
        calls.append("gate")
        return {"errors": s.get("inject_errors", 0)}

    def build(s):
        calls.append("build")
        return {"built": True}

    def report(s):
        calls.append("report")
        return {"gaps": ["x"] if not s.get("errors") else []}

    def fill(s):
        calls.append("fill")
        return {"filled": len(s.get("gaps", []))}

    return Plan(
        name="t", entry="gate",
        steps=(Step("gate", READ_ONLY, gate), Step("build", WRITES, build),
               Step("report", READ_ONLY, report), Step("fill", MODEL_CALL, fill)),
        edges=(Edge("gate", "build", when=lambda s: not s["errors"]),
               Edge("gate", "report"),
               Edge("build", "report"),
               Edge("report", "fill", when=lambda s: s.get("fix_gaps") and s.get("gaps")),
               Edge("report", END),
               Edge("fill", END)))


# --- registry + routing + dry-run guard ---------------------------------------

def test_registry_default_and_listing():
    assert DEFAULT_RUNTIME == "inprocess"
    assert list_runtimes() == ["inprocess", "langgraph"]   # registered != installed
    assert get_runtime().name == "inprocess"
    assert get_runtime("inprocess").name == "inprocess"


def test_unknown_runtime_raises_keyerror():
    with pytest.raises(KeyError):
        get_runtime("does-not-exist")


def test_dry_run_skips_gated_steps_and_never_calls_them():
    calls = []
    res = _rt().run(_branching_plan(calls), {"fix_gaps": True}, execute=False)
    assert "build" not in calls and "fill" not in calls
    assert calls == ["gate", "report"]
    assert res.state.get("built") is None and res.state.get("filled") is None
    assert res.status == COMPLETED
    skipped = {t.step: t.skipped_reason for t in res.trace if not t.ran}
    assert skipped == {"build": "dry-run", "fill": "dry-run"}


def test_execute_runs_full_clean_path():
    calls = []
    res = _rt().run(_branching_plan(calls), {"fix_gaps": True}, execute=True)
    assert calls == ["gate", "build", "report", "fill"]
    assert res.state["built"] is True and res.state["filled"] == 1
    assert all(t.ran for t in res.trace)


def test_conditional_edge_takes_dirty_branch():
    calls = []
    res = _rt().run(_branching_plan(calls),
                    {"inject_errors": 2, "fix_gaps": True}, execute=True)
    assert calls == ["gate", "report"]
    assert res.state["errors"] == 2 and res.state["gaps"] == []


def test_step_lookup_missing_raises():
    with pytest.raises(KeyError):
        _branching_plan([]).step("nope")


# --- visualization ------------------------------------------------------------

def test_to_mermaid_renders_the_graph():
    mer = _branching_plan([]).to_mermaid()
    assert mer.splitlines()[0] == "flowchart TD"
    assert "gate (read-only)" in mer and "fill (model-call)" in mer
    assert "_END" in mer            # terminal node
    assert "-.->" in mer            # at least one conditional (dashed) edge


# --- streaming ----------------------------------------------------------------

def test_on_event_streams_every_step_in_order():
    seen = []
    calls = []
    _rt().run(_branching_plan(calls), {"fix_gaps": True}, execute=True,
              on_event=lambda e: seen.append((e["step"], e["ran"])))
    assert seen == [("gate", True), ("build", True), ("report", True), ("fill", True)]


def test_on_event_reports_skipped_in_dry_run():
    seen = []
    _rt().run(_branching_plan([]), {"fix_gaps": True}, execute=False,
              on_event=lambda e: seen.append((e["step"], e["ran"], e["skipped_reason"])))
    assert ("build", False, "dry-run") in seen and ("fill", False, "dry-run") in seen


# --- fan-out (map step) -------------------------------------------------------

def _square_plan():
    def body(s):
        return {"sq": s["item"] ** 2}
    return Plan("f", "src",
                (Step("src", READ_ONLY, lambda s: {}),
                 Step("sq", WRITES, body, fan_out=lambda s: s["nums"])),
                (Edge("src", "sq"), Edge("sq", END)))


def test_fan_out_maps_in_item_order():
    res = _rt().run(_square_plan(), {"nums": [1, 2, 3, 4]}, execute=True)
    assert res.state["sq"] == [{"sq": 1}, {"sq": 4}, {"sq": 9}, {"sq": 16}]
    # a fan-out is ONE logical step in the trace
    assert [t.step for t in res.trace] == ["src", "sq"]


def test_fan_out_skipped_in_dry_run():
    res = _rt().run(_square_plan(), {"nums": [1, 2, 3]}, execute=False)
    assert "sq" not in res.state                      # body never ran
    assert any(t.step == "sq" and not t.ran for t in res.trace)


# --- durability (checkpoint + resume) -----------------------------------------

def _linear_plan(spy=None):
    def mk(key, val):
        def fn(s):
            if spy is not None:
                spy.append(key)
            return {key: val}
        return fn
    return Plan("d", "s1",
                (Step("s1", WRITES, mk("a", 1)),
                 Step("s2", WRITES, mk("b", 2)),
                 Step("s3", WRITES, mk("c", 3))),
                (Edge("s1", "s2"), Edge("s2", "s3"), Edge("s3", END)))


def test_checkpointer_writes_each_step_then_clears_on_completion():
    cp = MemoryCheckpointer()
    res = _rt().run(_linear_plan(), {}, execute=True, checkpointer=cp, run_key="k")
    assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
    assert cp.load("k") is None      # cleared once the run completed


def test_resume_after_a_crash_continues_from_the_checkpoint():
    spy = []
    plan = _linear_plan(spy)
    # make s2 fail exactly once
    boom = {"n": 0}
    original = plan.step("s2").run

    def flaky(s):
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("crash")
        return original(s)

    plan = Plan(plan.name, plan.entry,
                (plan.step("s1"), Step("s2", WRITES, flaky), plan.step("s3")),
                plan.edges)
    cp = MemoryCheckpointer()
    with pytest.raises(RuntimeError):
        _rt().run(plan, {}, execute=True, checkpointer=cp, run_key="k")
    snap = cp.load("k")
    assert snap is not None and snap["cursor"] == "s2"   # crashed before s2 committed
    res = _rt().run(plan, {}, execute=True, checkpointer=cp, run_key="k", resume=None)
    assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
    assert spy.count("a") == 1       # s1 (writes "a") NOT re-run on resume


def test_resume_without_checkpointer_is_an_error():
    with pytest.raises(RuntimeError):
        _rt().run(_linear_plan(), {}, execute=True, resume="x")


# --- human-in-the-loop (pause / resume) ---------------------------------------

def _approval_plan():
    def ask(s):
        decision = interrupt(s, {"question": "approve?", "gaps": s.get("gaps", [])})
        return {"approved": decision}
    return Plan("h", "prep",
                (Step("prep", READ_ONLY, lambda s: {"gaps": ["g1", "g2"]}),
                 Step("ask", MODEL_CALL, ask),
                 Step("act", WRITES, lambda s: {"acted": s["approved"]})),
                (Edge("prep", "ask"), Edge("ask", "act"), Edge("act", END)))


def test_interrupt_pauses_then_resumes_with_value():
    cp = MemoryCheckpointer()
    paused = _rt().run(_approval_plan(), {}, execute=True, checkpointer=cp, run_key="h")
    assert paused.status == PAUSED
    assert paused.interrupt == {"question": "approve?", "gaps": ["g1", "g2"]}
    assert "approved" not in paused.state           # the paused step did not commit
    resumed = _rt().run(_approval_plan(), {}, execute=True, checkpointer=cp,
                        run_key="h", resume="YES")
    assert resumed.status == COMPLETED
    assert resumed.state["approved"] == "YES" and resumed.state["acted"] == "YES"


def test_interrupt_outside_a_run_is_an_error():
    with pytest.raises(RuntimeError):
        interrupt({}, {"q": "x"})
'''
_RT_TEST_EQUIV_SRC = r'''"""
title: Unit — runtime conformance (inprocess == langgraph)
kind: tests
layer: backend
summary: Pins the LangGraph adapter as execution-only — identical state, trace, status, fan-out order, durability, and human-in-the-loop across engines.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from runtimes import (  # noqa: E402
    COMPLETED,
    END,
    MODEL_CALL,
    PAUSED,
    READ_ONLY,
    WRITES,
    Edge,
    MemoryCheckpointer,
    Plan,
    Step,
    get_runtime,
    interrupt,
)

pytestmark = pytest.mark.unit

# The LangGraph engine is an optional extra (pip install -e '.[langgraph]').
# Without it, the inprocess tests still run; this whole module skips.
pytest.importorskip("langgraph")

ENGINES = ("inprocess", "langgraph")


# --- branching + dry-run guard ------------------------------------------------

def _branching(calls):
    def gate(s):
        calls.append("gate")
        return {"errors": s.get("inject_errors", 0)}

    def build(s):
        calls.append("build")
        return {"built": True}

    def report(s):
        calls.append("report")
        return {"gaps": ["a", "b"] if not s.get("errors") else []}

    def fill(s):
        calls.append("fill")
        return {"filled": len(s.get("gaps", []))}

    return Plan("conf", "gate",
                (Step("gate", READ_ONLY, gate), Step("build", WRITES, build),
                 Step("report", READ_ONLY, report), Step("fill", MODEL_CALL, fill)),
                (Edge("gate", "build", when=lambda s: not s["errors"]),
                 Edge("gate", "report"), Edge("build", "report"),
                 Edge("report", "fill", when=lambda s: s.get("fix_gaps") and s.get("gaps")),
                 Edge("report", END), Edge("fill", END)))


_SCENARIOS = [
    ("dry_fix", {"fix_gaps": True}, False),
    ("exec_fix", {"fix_gaps": True}, True),
    ("exec_dirty", {"inject_errors": 3, "fix_gaps": True}, True),
    ("exec_nofix", {}, True),
    ("dry_nofix", {}, False),
]


def _run(engine, init, execute):
    calls = []
    res = get_runtime(engine).run(_branching(calls), dict(init), execute=execute)
    trace = [(t.step, t.ran, t.skipped_reason) for t in res.trace]
    return res.state, trace, res.status, calls


@pytest.mark.parametrize("label,init,execute", _SCENARIOS, ids=[s[0] for s in _SCENARIOS])
def test_branching_equivalence(label, init, execute):
    a = _run("inprocess", init, execute)
    b = _run("langgraph", init, execute)
    assert a == b   # state, trace, status, and which bodies ran — all identical


def test_dry_run_guard_holds_on_both_engines():
    for engine in ENGINES:
        _, _, _, calls = _run(engine, {"fix_gaps": True}, False)
        assert "build" not in calls and "fill" not in calls, engine


# --- fan-out (map): same ordered result on both engines -----------------------

def _fan_plan():
    return Plan("f", "src",
                (Step("src", READ_ONLY, lambda s: {}),
                 Step("sq", WRITES, lambda s: {"sq": s["item"] ** 2},
                      fan_out=lambda s: s["nums"])),
                (Edge("src", "sq"), Edge("sq", END)))


def test_fan_out_equivalence_ordered():
    nums = [3, 1, 4, 1, 5, 9, 2, 6]
    a = get_runtime("inprocess").run(_fan_plan(), {"nums": nums}, execute=True)
    b = get_runtime("langgraph").run(_fan_plan(), {"nums": nums}, execute=True)
    # LangGraph Send runs items concurrently; results must still match item order
    assert a.state["sq"] == b.state["sq"] == [{"sq": n ** 2} for n in nums]
    assert [t.step for t in a.trace] == [t.step for t in b.trace] == ["src", "sq"]


# --- streaming: same events on both engines -----------------------------------

def test_streaming_equivalence():
    out = {}
    for engine in ENGINES:
        seen = []
        get_runtime(engine).run(_branching([]), {"fix_gaps": True}, execute=True,
                                on_event=lambda e: seen.append((e["step"], e["ran"])))
        out[engine] = seen
    assert out["inprocess"] == out["langgraph"]


# --- durability: full run completes + clears on both --------------------------

def test_durable_run_equivalence():
    def mk(k, v):
        return lambda s: {k: v}
    plan = Plan("d", "s1",
                (Step("s1", WRITES, mk("a", 1)), Step("s2", WRITES, mk("b", 2)),
                 Step("s3", WRITES, mk("c", 3))),
                (Edge("s1", "s2"), Edge("s2", "s3"), Edge("s3", END)))
    for engine in ENGINES:
        cp = MemoryCheckpointer()
        res = get_runtime(engine).run(plan, {}, execute=True, checkpointer=cp, run_key="k")
        assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
        assert cp.load("k") is None


# --- human-in-the-loop: same pause payload, same resumed state ----------------

def _approval_plan():
    def ask(s):
        return {"approved": interrupt(s, {"q": "approve?", "gaps": s.get("gaps", [])})}
    return Plan("h", "prep",
                (Step("prep", READ_ONLY, lambda s: {"gaps": ["g1", "g2"]}),
                 Step("ask", MODEL_CALL, ask),
                 Step("act", WRITES, lambda s: {"acted": s["approved"]})),
                (Edge("prep", "ask"), Edge("ask", "act"), Edge("act", END)))


def test_human_in_the_loop_equivalence():
    paused, resumed = {}, {}
    for engine in ENGINES:
        cp = MemoryCheckpointer()
        p = get_runtime(engine).run(_approval_plan(), {}, execute=True,
                                    checkpointer=cp, run_key="h")
        r = get_runtime(engine).run(_approval_plan(), {}, execute=True,
                                    checkpointer=cp, run_key="h", resume="OK")
        paused[engine] = (p.status, p.interrupt)
        resumed[engine] = (r.status, r.state)
    assert paused["inprocess"] == paused["langgraph"] == (PAUSED, {"q": "approve?", "gaps": ["g1", "g2"]})
    assert resumed["inprocess"] == resumed["langgraph"]
    assert resumed["inprocess"][1]["approved"] == "OK"
'''


# Source of scripts/check_structure.py. Kept 3.6-compatible (no future import,
# no walrus) so it runs under the host's default python3 as well as CI's 3.11.
_CHECK_STRUCTURE_SRC = r'''#!/usr/bin/env python3
"""
check_structure.py - enforce the project conventions (see CONVENTIONS.md).

Checks:
  A. Frontmatter validity on README.md / AGENT.md / CLAUDE.md, docs/**,
     test-docs/** *.md, and agents/**/*.tool.md
  B. Each taxonomy directory that exists has README.md + CLAUDE.md
  C. Each src/ directory containing *.py is a package: __init__.py with __all__
  D. The __init__ boundary: no absolute import of another package's _private module
  E. Authored coverage (WARN): every __all__-exported symbol has a docstring
  F. Tool specs governed (ERR) + accountability (WARN): tool/agent docs are owned
  G. Tool<->agent binding (ERR): tools.md <-> '## Used by' agree; tool_command invokes public_api
  H. Project facts in config/project.json agree with the tree (ERR); an
     undeclared leftover stack/transport dir WARNs (CONVENTIONS section 15).
     An optional 'runtimes' block is validated the same way (section 16)
  I. Agent-rules symlink (ERR): every CLAUDE.md is a symlink to its sibling
     AGENT.md, and every AGENT.md has that sibling (CONVENTIONS section 5)

Exit 0 = clean, 1 = errors. Warnings never fail the build. Stdlib only; 3.6+.
"""
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".astro", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

KINDS = {
    "readme", "rules", "package", "module", "tests", "test-doc", "doc", "spec",
    "design", "adr", "config", "script", "agent", "mcp", "api", "wiki", "demo",
    "model", "eval", "container", "ops",
    "tool",                      # agents/tools/*.tool.md adapters
}
TOOL_EFFECTS = {"read-only", "writes", "model-call"}
LAYERS = {"frontend", "backend", "shared", "app", "cross-cutting", "n/a"}
STATUSES = {
    "draft", "stable", "deprecated", "template",   # general lifecycle
    "proposed", "accepted", "superseded",          # ADR lifecycle
}
VISIBILITIES = {"public", "internal", "confidential", "restricted"}
REQUIRED_KEYS = ("title", "kind", "layer", "status", "summary",
                 "id", "created", "updated", "visibility", "canonical")

TAXONOMY = [
    "src", "tests", "test-docs", "docs", "agents", "mcp", "api", "wiki",
    "scripts", "config", "demo", "containers", "evals", "ops", "models",
    "runtimes",
]
REQUIRED_TOPLEVEL = ["src", "tests", "docs"]
CODE_ROOTS = ["src", "tests", "api", "models", "mcp", "agents", "demo",
              "scripts", "runtimes"]

errors = []
warnings = []
GOVERNED = []  # (relpath, kind, owner) for frontmatter docs check_A validated


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def rel(p):
    return os.path.relpath(p, ROOT)


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        yield dirpath, dirnames, filenames


def parse_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception as e:
        err("%s: cannot read (%s)" % (rel(path), e))
        return {}
    if not text.startswith("---"):
        return None
    data = {}
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            return data
        if line[:1] in (" ", "\t"):
            continue  # nested key (e.g. cdmon's cdm: sub-keys) - not top-level
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return None  # block never closed


def check_frontmatter(path, seen_ids):
    fm = parse_frontmatter(path)
    if fm is None:
        err("%s: missing or unterminated frontmatter block" % rel(path))
        return
    for k in REQUIRED_KEYS:
        if not fm.get(k):
            err("%s: frontmatter missing required key '%s'" % (rel(path), k))
    if fm.get("kind") and fm["kind"] not in KINDS:
        err("%s: invalid kind '%s'" % (rel(path), fm["kind"]))
    if fm.get("layer") and fm["layer"] not in LAYERS:
        err("%s: invalid layer '%s'" % (rel(path), fm["layer"]))
    if fm.get("status") and fm["status"] not in STATUSES:
        err("%s: invalid status '%s'" % (rel(path), fm["status"]))
    if fm.get("visibility") and fm["visibility"] not in VISIBILITIES:
        err("%s: invalid visibility '%s'" % (rel(path), fm["visibility"]))
    # Corpus: id must be unique across the corpus.
    fid = fm.get("id")
    if fid:
        if fid in seen_ids:
            err("%s: duplicate id '%s' (also in %s)" % (rel(path), fid, seen_ids[fid]))
        else:
            seen_ids[fid] = rel(path)
    # Corpus: a path-like canonical pointer must resolve to a real file.
    can = fm.get("canonical")
    if can and can not in ("true", "false", "self"):
        if ("/" in can or can.endswith(".md")) and \
                not os.path.exists(os.path.join(ROOT, can)):
            err("%s: canonical target '%s' does not exist" % (rel(path), can))
    # Corpus: deprecated content must point at its successor.
    if fm.get("status") == "deprecated" and not fm.get("superseded_by"):
        err("%s: status is 'deprecated' but no 'superseded_by' is set" % rel(path))
    if not fm.get("owner"):
        warn("%s: frontmatter missing 'owner'" % rel(path))


def check_A():
    seen_ids = {}
    seen_real = set()  # dedupe symlink + target (CLAUDE.md -> AGENT.md)
    for dirpath, _, filenames in walk(ROOT):
        top = rel(dirpath).split(os.sep)[0]
        in_docs = top in ("docs", "test-docs")
        for f in filenames:
            is_tool = f.endswith(".tool.md") and top == "agents"
            if f in ("README.md", "AGENT.md", "CLAUDE.md") \
                    or (in_docs and f.endswith(".md")) or is_tool:
                full = os.path.join(dirpath, f)
                real = os.path.realpath(full)
                if real in seen_real:
                    continue
                seen_real.add(real)
                check_frontmatter(full, seen_ids)
                fm = parse_frontmatter(full)   # cheap re-parse for the roll-up
                if fm:
                    GOVERNED.append((rel(full), fm.get("kind"), fm.get("owner")))


def check_B():
    for d in REQUIRED_TOPLEVEL:
        if not os.path.isdir(os.path.join(ROOT, d)):
            err("required top-level dir '%s/' is missing" % d)
    for d in TAXONOMY:
        full = os.path.join(ROOT, d)
        if os.path.isdir(full):
            for need in ("README.md", "CLAUDE.md"):
                if not os.path.isfile(os.path.join(full, need)):
                    err("%s/: missing %s" % (d, need))


def check_C():
    srcroot = os.path.join(ROOT, "src")
    if not os.path.isdir(srcroot):
        return
    for dirpath, _, filenames in walk(srcroot):
        if not any(f.endswith(".py") for f in filenames):
            continue
        if "__init__.py" not in filenames:
            err("%s/: has .py files but no __init__.py (package boundary)"
                % rel(dirpath))
            continue
        init = os.path.join(dirpath, "__init__.py")
        try:
            with open(init, encoding="utf-8") as fh:
                if "__all__" not in fh.read():
                    err("%s: __init__.py defines no __all__ (public API surface)"
                        % rel(init))
        except Exception as e:
            err("%s: cannot read (%s)" % (rel(init), e))


def _private_segment(dotted):
    if not dotted:
        return False
    for part in dotted.split("."):
        if part.startswith("_") and not part.startswith("__"):
            return True
    return False


def check_D():
    for croot in CODE_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read(), filename=full)
                except Exception as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.level == 0 and _private_segment(node.module):
                            err("%s:%d: absolute import of private module '%s' "
                                "crosses a package boundary - import from the "
                                "package public API instead"
                                % (rel(full), node.lineno, node.module))
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if _private_segment(alias.name):
                                err("%s:%d: import of private module '%s' "
                                    "crosses a package boundary"
                                    % (rel(full), node.lineno, alias.name))


def _exported_names(tree):
    """Return the string elements of a top-level __all__ literal, or []."""
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" \
                        and isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        val = getattr(elt, "s", None)          # 3.6 ast.Str
                        if val is None and isinstance(elt, ast.Constant):
                            val = elt.value                     # 3.8+ ast.Constant
                        if isinstance(val, str):
                            out.append(val)
    return out


def check_E():
    """WARN when an __all__-exported symbol defined in-file has no docstring.
    Authored docstrings are the canonical corpus summaries; flag the gaps."""
    for croot in CODE_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read(), filename=full)
                except Exception:
                    continue  # check_D already warns on parse failure
                exported = _exported_names(tree)
                if not exported:
                    continue
                defs = {}
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                        defs[node.name] = node
                for name in sorted(exported):
                    nd = defs.get(name)   # only names DEFINED here (skip re-exports)
                    if nd is not None and not ast.get_docstring(nd):
                        warn("%s: exported symbol '%s' has no docstring "
                             "(authored summary missing)" % (rel(full), name))


def check_F():
    """ERROR on malformed tool specs; WARN when tool/agent docs lack a real owner."""
    agents_dir = os.path.join(ROOT, "agents")
    if os.path.isdir(agents_dir):
        # Validate EVERY *.tool.md under agents/ (not just agents/tools/), so a
        # misplaced/malformed spec cannot dodge governance.
        for dirpath, _, filenames in walk(agents_dir):
            for f in sorted(filenames):
                if not f.endswith(".tool.md"):
                    continue
                full = os.path.join(dirpath, f)
                fm = parse_frontmatter(full)
                if not fm:
                    continue  # check_A already errored on bad/missing frontmatter
                if fm.get("kind") != "tool":
                    err("%s: tool spec must have kind 'tool'" % rel(full))
                inv = fm.get("public_api")
                if not inv or inv == "none":
                    err("%s: tool spec missing 'public_api' (the wrapped script)"
                        % rel(full))
                elif not os.path.exists(os.path.join(ROOT, inv)):
                    err("%s: public_api target '%s' does not exist" % (rel(full), inv))
                eff = fm.get("tool_effect")
                if eff not in TOOL_EFFECTS:
                    err("%s: tool_effect must be one of %s"
                        % (rel(full), sorted(TOOL_EFFECTS)))
                cmd = fm.get("tool_command") or ""
                if inv and inv != "none" and inv not in cmd:
                    err("%s: tool_command does not invoke public_api '%s'"
                        % (rel(full), inv))
    # accountability roll-up (warning): tools/agents must name a real owner
    for path, kind, owner in GOVERNED:
        if kind in ("tool", "agent") and (not owner or owner == "TBD"):
            warn("accountability: %s (%s) has no real owner (missing or 'TBD')"
                 % (path, kind))


def _tool_used_by(path):
    """Agent dirs (agents/<name>) listed under a tool spec's '## Used by'."""
    out = []
    in_section = False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("## "):
                    in_section = s.lower() == "## used by"
                    continue
                if in_section and s.startswith("- "):
                    ref = s[2:].strip().rstrip("/")
                    if ref.startswith("agents/"):
                        out.append(ref)
    except Exception:
        pass
    return out


def _manifest_specs(path):
    """Tool-spec basenames referenced in an agent's tools.md (../tools/X.tool.md)."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return out
    marker, end = "../tools/", ".tool.md"
    i = 0
    while True:
        j = text.find(marker, i)
        if j < 0:
            break
        k = text.find(end, j)
        if k < 0:
            break
        out.append(text[j + len(marker):k])
        i = k + 1
    return out


def check_G():
    """Enforce the bidirectional tool<->agent binding (CONVENTIONS §10)."""
    agents_dir = os.path.join(ROOT, "agents")
    tools_dir = os.path.join(agents_dir, "tools")
    if not os.path.isdir(agents_dir):
        return
    existing = set()
    if os.path.isdir(tools_dir):
        for f in os.listdir(tools_dir):
            if f.endswith(".tool.md"):
                existing.add(f[:-len(".tool.md")])
    spec_to_agents = {}
    for s in existing:
        spec_to_agents[s] = set(_tool_used_by(os.path.join(tools_dir, s + ".tool.md")))
    agent_to_specs = {}
    for name in sorted(os.listdir(agents_dir)):
        man = os.path.join(agents_dir, name, "tools.md")
        if name == "tools" or not os.path.isfile(man):
            continue
        agent_to_specs["agents/" + name] = set(_manifest_specs(man))
    for agent, specs in agent_to_specs.items():
        for s in specs:
            if s not in existing:
                err("%s/tools.md: references unknown tool spec "
                    "'../tools/%s.tool.md'" % (agent, s))
            elif agent not in spec_to_agents.get(s, set()):
                err("%s/tools.md: uses '%s' but agents/tools/%s.tool.md "
                    "'## Used by' omits %s" % (agent, s, s, agent))
    for s in sorted(spec_to_agents):
        for agent in spec_to_agents[s]:
            if s not in agent_to_specs.get(agent, set()):
                err("agents/tools/%s.tool.md: '## Used by' names %s but its "
                    "tools.md omits '%s'" % (s, agent, s))


def _requires_python():
    """Return pyproject.toml's requires-python value, or None if absent."""
    try:
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return None
    m = re.search(r'requires-python\s*=\s*(["\'])([^"\']+)\1', text)
    return m.group(2).strip() if m else None


def _subdirs(relpath):
    """Immediate sub-directory names under ROOT/relpath, minus IGNORE_DIRS."""
    base = os.path.join(ROOT, relpath)
    out = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name not in IGNORE_DIRS and os.path.isdir(os.path.join(base, name)):
                out.append(name)
    return out


def _expect(val, typ, label, default):
    """Return val if it is `typ` (None becomes default); else record an error.

    A malformed manifest gets a clean error, never a traceback or a silent
    pass (e.g. an 'available' written as an object instead of a list).
    """
    if val is None:
        return default
    if not isinstance(val, typ):
        want = "a list" if typ is list else "an object" if typ is dict else typ.__name__
        err("config/project.json: %s must be %s" % (label, want))
        return default
    return val


def check_H():
    """Project facts in config/project.json agree with the tree.

    Declared facts are enforced (errors); a stack or transport present on
    disk but absent from the manifest is a WARN (an undeclared leftover).
    Stdlib JSON, so it runs under the old pre-commit interpreter (no tomllib).
    See CONVENTIONS section 15.
    """
    path = os.path.join(ROOT, "config", "project.json")
    if not os.path.isfile(path):
        warn("config/project.json: not found; project facts are unenforced")
        return
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception as e:
        err("config/project.json: invalid JSON (%s)" % e)
        return
    if not isinstance(manifest, dict):
        err("config/project.json: top level must be a JSON object")
        return
    layers = _expect(manifest.get("layers"), dict, "layers", {})

    backend = _expect(layers.get("backend"), dict, "layers.backend", {})
    bpath = backend.get("path")
    if isinstance(bpath, str) and bpath and not os.path.isdir(os.path.join(ROOT, bpath)):
        err("config/project.json: layers.backend.path '%s' does not exist" % bpath)
    bpy = backend.get("python")
    if isinstance(bpy, str) and bpy:
        have = _requires_python()
        if have is not None and have != bpy:
            err("config/project.json: layers.backend.python '%s' != pyproject "
                "requires-python '%s'" % (bpy, have))

    frontend = _expect(layers.get("frontend"), dict, "layers.frontend", {})
    froot = frontend.get("root")
    if isinstance(froot, str) and froot:
        available = _expect(frontend.get("available"), list,
                            "layers.frontend.available", [])
        stack = frontend.get("stack")
        if isinstance(stack, str) and stack \
                and not os.path.isdir(os.path.join(ROOT, froot, stack)):
            err("config/project.json: layers.frontend.stack '%s' has no dir "
                "under %s/" % (stack, froot))
        for a in available:
            if isinstance(a, str) and not os.path.isdir(os.path.join(ROOT, froot, a)):
                warn("config/project.json: declared frontend stack '%s' is "
                     "missing (%s/%s)" % (a, froot, a))
        for d in _subdirs(froot):
            if d not in available:
                warn("%s/%s: present but not in config/project.json "
                     "layers.frontend.available (undeclared stack)" % (froot, d))

    transports = _expect(manifest.get("transports"), dict, "transports", {})
    enabled = _expect(transports.get("enabled"), list, "transports.enabled", [])
    avail = _expect(transports.get("available"), dict, "transports.available", {})
    for t in enabled:
        if t not in avail:
            err("config/project.json: transports.enabled '%s' not in "
                "transports.available" % t)
        elif isinstance(avail[t], str) \
                and not os.path.isdir(os.path.join(ROOT, avail[t])):
            err("config/project.json: enabled transport '%s' -> '%s' does not "
                "exist" % (t, avail[t]))
    declared = set(v for v in avail.values() if isinstance(v, str))
    for d in _subdirs("api"):
        if os.path.join("api", d) not in declared:
            warn("api/%s: present but not in config/project.json "
                 "transports.available (undeclared transport)" % d)

    # Agent runtimes (optional block): the default must be an available engine
    # and each engine's dir must exist (CONVENTIONS section 16).
    runtimes = manifest.get("runtimes")
    if runtimes is not None:
        runtimes = _expect(runtimes, dict, "runtimes", {})
        r_avail = _expect(runtimes.get("available"), dict, "runtimes.available", {})
        r_default = runtimes.get("default")
        if r_default is not None and r_default not in r_avail:
            err("config/project.json: runtimes.default '%s' not in "
                "runtimes.available" % r_default)
        for nm in sorted(r_avail):
            d = r_avail[nm]
            if isinstance(d, str) and not os.path.isdir(os.path.join(ROOT, d)):
                err("config/project.json: runtime '%s' -> '%s' does not exist"
                    % (nm, d))


def check_I():
    """ERROR when CLAUDE.md is not a symlink to its sibling AGENT.md.

    CONVENTIONS section 5: AGENT.md is the canonical, vendor-neutral agent-rules
    file; CLAUDE.md is a symlink to it so every agent tool reads one source. A
    regular-file CLAUDE.md is a copy that drifts silently -- require the link.
    Also flag an AGENT.md with no CLAUDE.md sibling (rules an agent can't find).
    """
    for dirpath, _, filenames in walk(ROOT):
        has_agent = "AGENT.md" in filenames
        if "CLAUDE.md" in filenames:
            claude = os.path.join(dirpath, "CLAUDE.md")
            if not os.path.islink(claude):
                err("%s: must be a symlink to the sibling AGENT.md, not a "
                    "regular file (CONVENTIONS section 5)" % rel(claude))
            elif os.readlink(claude) != "AGENT.md":
                err("%s: symlink target '%s' must be exactly 'AGENT.md' "
                    "(a relative sibling link)" % (rel(claude), os.readlink(claude)))
            elif not os.path.isfile(os.path.join(dirpath, "AGENT.md")):
                err("%s: symlink target AGENT.md does not exist" % rel(claude))
        elif has_agent:
            err("%s/AGENT.md: has no sibling CLAUDE.md symlink "
                "(CONVENTIONS section 5)" % rel(dirpath))


def main():
    check_A()
    check_B()
    check_C()
    check_D()
    check_E()
    check_F()
    check_G()
    check_H()
    check_I()
    for w_ in warnings:
        print("WARN  " + w_)
    for e_ in errors:
        print("ERROR " + e_)
    print("")
    print("check_structure: %d error(s), %d warning(s)"
          % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
'''


# Source of scripts/check_scaffold_sync.py — guards that the embed above
# stays byte-identical to the live checker (CONVENTIONS section 6). Built to
# contain no triple-single-quote so it embeds cleanly here too.
_CHECK_SCAFFOLD_SYNC_SRC = r'''#!/usr/bin/env python3
"""
check_scaffold_sync.py - guard that scaffold.py's embedded scripts stay in sync.

scripts/scaffold.py regenerates the project skeleton, and it ships several
support scripts as embedded raw-string constants, e.g.

    w("scripts/check_structure.py", _CHECK_STRUCTURE_SRC)
    ...
    _CHECK_STRUCTURE_SRC = r<TRI>...<TRI>      # <TRI> = three single quotes

CONVENTIONS.md (section 6) requires the live `scripts/check_structure.py` and
its embedded copy to stay *byte-identical*; the same must hold for every other
script the scaffold embeds, or a freshly scaffolded project ships tooling that
has silently diverged from the one this repo runs in CI.

This script makes that machine-checked for ALL embedded scripts (it discovers
them by parsing the `w("path", _NAME_SRC)` pairs), not just one:

  --check   (default) exit 1 if any embed differs from its live file; prints diffs.
  --write             rewrite every embed from its live file (the fix).

If scripts/scaffold.py is absent (e.g. a derived project that didn't keep the
generator), there is nothing to guard, so this is a no-op exit 0 -- the same
graceful-skip pattern cdmon_sync.py and the AAD schema check use.

A doer, not a trigger (CONVENTIONS section 7). Stdlib only; runs on Python 3.6+.
"""
import argparse
import difflib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")
TRI = "'" * 3  # built at runtime so THIS file embeds cleanly (no literal triple-quote)

# scaffold emits an embedded script as:  w("relpath", _NAME_SRC)
_W_RE = re.compile(r'w\(\s*"([^"]+)"\s*,\s*(_[A-Z0-9_]+_SRC)\s*\)')


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _embeds(scaffold_text):
    """Yield (relpath, const_name, embedded_source) for each embedded script.

    Deduped by constant: an example `w("...", _NAME_SRC)` inside an embedded
    docstring must not double-count a real embed. A constant is an embed only
    if it has a real top-level `_NAME_SRC = r<TRI>...<TRI>` definition.
    """
    seen = set()
    for relpath, const in _W_RE.findall(scaffold_text):
        if const in seen:
            continue
        m = re.search(re.escape(const) + r" = r" + TRI + r"(.*?)" + TRI,
                      scaffold_text, re.DOTALL)
        if m:
            seen.add(const)
            yield relpath, const, m.group(1)


def check():
    """Return 0 when every embed matches its live file, else 1 (prints diffs)."""
    if not os.path.isfile(SCAFFOLD):
        print("check_scaffold_sync: no scripts/scaffold.py; nothing to guard (skip)")
        return 0
    pairs = list(_embeds(_read(SCAFFOLD)))
    if not pairs:
        sys.stderr.write("ERROR check_scaffold_sync: found no embedded scripts "
                         "(w(\"...\", _NAME_SRC)) in scripts/scaffold.py\n")
        return 1
    bad = 0
    for relpath, const, embedded in pairs:
        live_path = os.path.join(ROOT, relpath)
        try:
            live = _read(live_path)
        except OSError:
            sys.stderr.write("ERROR check_scaffold_sync: %s embeds %s but the "
                             "live file is missing\n" % (const, relpath))
            bad += 1
            continue
        if embedded == live:
            continue
        bad += 1
        sys.stderr.write(
            "ERROR check_scaffold_sync: %s (embed %s) has drifted from the live "
            "file. Run `python3 scripts/check_scaffold_sync.py --write` to "
            "resync (CONVENTIONS section 6).\n\n" % (relpath, const))
        diff = difflib.unified_diff(
            live.splitlines(), embedded.splitlines(),
            "%s (live)" % relpath, "scaffold.py:%s (embedded)" % const, lineterm="")
        for i, line in enumerate(diff):
            sys.stderr.write(line + "\n")
            if i > 120:
                sys.stderr.write("... (diff truncated)\n")
                break
        sys.stderr.write("\n")
    if bad:
        return 1
    print("check_scaffold_sync: %d embedded script(s) match their live files"
          % len(pairs))
    return 0


def write():
    """Rewrite every embed in scaffold.py from its live file. Returns 0/1."""
    if not os.path.isfile(SCAFFOLD):
        print("check_scaffold_sync: no scripts/scaffold.py; nothing to write (skip)")
        return 0
    text = _read(SCAFFOLD)
    pairs = list(_embeds(text))
    if not pairs:
        sys.stderr.write("ERROR check_scaffold_sync: no embedded scripts to "
                         "rewrite in scripts/scaffold.py\n")
        return 1
    changed = 0
    for relpath, const, _embedded in pairs:
        live = _read(os.path.join(ROOT, relpath))
        if TRI in live:
            sys.stderr.write("ERROR check_scaffold_sync: %s contains a "
                             "triple-single-quote sequence, which would break "
                             "its raw-string embed. Remove it.\n" % relpath)
            return 1
        pat = re.compile(re.escape(const) + r" = r" + TRI + r".*?" + TRI, re.DOTALL)
        repl = const + " = r" + TRI + live + TRI
        new = pat.sub(lambda _m: repl, text, count=1)
        if new != text:
            changed += 1
            text = new
    with open(SCAFFOLD, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("check_scaffold_sync: resynced %d embedded script(s) in scripts/scaffold.py"
          % changed)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Keep scaffold.py's embedded scripts byte-identical to their "
                    "live files (CONVENTIONS section 6).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", default=True,
                   help="fail if any embed differs (default)")
    g.add_argument("--write", action="store_true",
                   help="rewrite every embed from its live file")
    args = ap.parse_args(argv)
    return write() if args.write else check()


if __name__ == "__main__":
    sys.exit(main())
'''

# Source of scripts/jobs/check_corpus.py — corpus integrity + build determinism.
_CHECK_CORPUS_SRC = r'''#!/usr/bin/env python3
"""
title: Check corpus job
kind: script
layer: n/a
summary: Deterministic: validate wiki/corpus.json integrity and that build is reproducible.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from build_corpus import build_corpus            # noqa: E402
from link_corpus import link_corpus              # noqa: E402

# Allowed enum values for the corpus contract (CONVENTIONS section 11/12).
KINDS = {"doc", "section", "module", "symbol"}
OWNER_SOURCES = {"frontmatter", "marker", "inherited", "none"}
SUMMARY_SOURCES = {"authored", "generated", ""}
VISIBILITIES = {"public", "internal", "confidential", "restricted"}
LINK_SOURCES = {"deterministic", "generated"}
REQUIRED_FIELDS = (
    "node_id", "kind", "title", "path", "anchor", "lineno", "summary",
    "summary_source", "text_excerpt", "owner", "owner_source", "owner_origin",
    "tags", "visibility", "updated", "parent", "children", "links",
)
SCHEMA_VERSION = 1


def _dumps(corpus: dict) -> str:
    """Canonical serialization (matches build_corpus/link_corpus on-disk form)."""
    return json.dumps(corpus, indent=2, sort_keys=True) + "\n"


def validate(corpus: dict) -> list:
    """Return a list of human-readable integrity errors ([] when the graph is valid)."""
    errs = []

    def e(msg):
        errs.append(msg)

    if not isinstance(corpus, dict):
        return ["corpus is not a JSON object"]
    if corpus.get("schema_version") != SCHEMA_VERSION:
        e("schema_version is %r, expected %d"
          % (corpus.get("schema_version"), SCHEMA_VERSION))
    nodes = corpus.get("nodes")
    if not isinstance(nodes, list):
        return errs + ["'nodes' missing or not a list"]

    by_id = {}
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            e("node[%d] is not an object" % i)
            continue
        nid = n.get("node_id")
        for f in REQUIRED_FIELDS:
            if f not in n:
                e("node %r missing required field '%s'" % (nid, f))
        if nid in by_id:
            e("duplicate node_id %r (primary key must be unique)" % nid)
        else:
            by_id[nid] = n
        if n.get("kind") not in KINDS:
            e("node %r has invalid kind %r (expected %s)"
              % (nid, n.get("kind"), sorted(KINDS)))
        if n.get("owner_source") not in OWNER_SOURCES:
            e("node %r has invalid owner_source %r" % (nid, n.get("owner_source")))
        if n.get("summary_source") not in SUMMARY_SOURCES:
            e("node %r has invalid summary_source %r" % (nid, n.get("summary_source")))
        if n.get("visibility") not in VISIBILITIES:
            e("node %r has invalid visibility %r" % (nid, n.get("visibility")))
        # owner/owner_source coherence (CONVENTIONS section 12)
        if n.get("owner_source") == "none":
            if n.get("owner"):
                e("node %r: owner_source 'none' but owner is %r" % (nid, n.get("owner")))
            if n.get("owner_origin") is not None:
                e("node %r: owner_source 'none' but owner_origin is set" % nid)
        else:
            if not n.get("owner"):
                e("node %r: owner_source %r but owner is empty"
                  % (nid, n.get("owner_source")))
        tags = n.get("tags")
        if not isinstance(tags, list):
            e("node %r: tags is not a list" % nid)
        elif tags != sorted(set(tags)):
            e("node %r: tags must be sorted and unique" % nid)

    # Reference + tree integrity (needs the full id set first).
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("node_id")
        parent = n.get("parent")
        if parent is not None:
            if parent not in by_id:
                e("node %r: parent %r does not resolve" % (nid, parent))
            elif nid not in by_id[parent].get("children", []):
                e("node %r: parent %r does not list it as a child (broken tree edge)"
                  % (nid, parent))
        for c in n.get("children", []) or []:
            if c not in by_id:
                e("node %r: child %r does not resolve" % (nid, c))
            elif by_id[c].get("parent") != nid:
                e("node %r: child %r has a different parent (broken tree edge)"
                  % (nid, c))
        for ln in n.get("links", []) or []:
            if not isinstance(ln, dict):
                e("node %r: a link is not an object" % nid)
                continue
            if ln.get("to") not in by_id:
                e("node %r: link target %r does not resolve" % (nid, ln.get("to")))
            if ln.get("source") not in LINK_SOURCES:
                e("node %r: link source %r invalid" % (nid, ln.get("source")))
            sc = ln.get("score")
            if not isinstance(sc, (int, float)) or not (0.0 <= sc <= 1.0):
                e("node %r: link score %r out of [0,1]" % (nid, sc))

    # Acyclicity of the parent chain.
    for n in nodes:
        if not isinstance(n, dict):
            continue
        seen, cur = set(), n.get("node_id")
        while cur is not None and cur in by_id:
            if cur in seen:
                e("node %r: parent chain has a cycle" % n.get("node_id"))
                break
            seen.add(cur)
            cur = by_id[cur].get("parent")
    return errs


def _fresh(root: str, max_links: int) -> dict:
    return link_corpus(build_corpus(root), max_links=max_links)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate corpus integrity and build reproducibility "
                    "(deterministic; CONVENTIONS section 11).")
    ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
    ap.add_argument("--corpus", default=None,
                    help="validate this existing corpus file instead of a fresh "
                         "build; also warns if it is stale vs a fresh build")
    ap.add_argument("--max-links", type=int, default=8, help="max edges per node")
    args = ap.parse_args(argv)

    rc = 0
    if args.corpus:
        path = args.corpus if os.path.isabs(args.corpus) \
            else os.path.join(args.root, args.corpus)
        if not os.path.exists(path):
            sys.stderr.write("ERROR check_corpus: no corpus at %s\n" % args.corpus)
            return 1
        with open(path, encoding="utf-8") as fh:
            corpus = json.load(fh)
        errs = validate(corpus)
        for m in errs:
            sys.stderr.write("ERROR check_corpus: %s\n" % m)
        rc = 1 if errs else 0
        # The file is a generated view (gitignored); staleness is a warning.
        if _dumps(corpus) != _dumps(_fresh(args.root, args.max_links)):
            print("WARN check_corpus: %s is stale vs a fresh build "
                  "(regenerate via rebuild_index.py)" % args.corpus)
        if rc == 0:
            print("check_corpus: %s valid (%d nodes)"
                  % (args.corpus, len(corpus.get("nodes", []))))
        return rc

    # Default: build fresh, validate integrity, then prove reproducibility.
    first = _fresh(args.root, args.max_links)
    errs = validate(first)
    for m in errs:
        sys.stderr.write("ERROR check_corpus: %s\n" % m)
    if errs:
        rc = 1
    second = _fresh(args.root, args.max_links)
    if _dumps(first) != _dumps(second):
        sys.stderr.write("ERROR check_corpus: build is NOT deterministic "
                         "(two builds differ)\n")
        rc = 1
    if rc == 0:
        print("check_corpus: fresh build valid + deterministic (%d nodes, %d edges)"
              % (len(first["nodes"]),
                 sum(len(n.get("links", [])) for n in first["nodes"])))
    return rc


if __name__ == "__main__":
    sys.exit(main())
'''


# --- embedded sources for wiki_agents() (generated from verified files) ---

_BUILD_CORPUS_SRC = r'''
#!/usr/bin/env python3
"""
title: Build corpus job
kind: script
layer: n/a
summary: Deterministic: walk the repo into wiki/corpus.json (the one-brain index).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_VERSION = 1

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".astro", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
CODE_ROOTS = ["src", "tests", "api", "models", "mcp", "agents", "demo", "scripts"]

# Owner markers use the same token + grammar in both worlds, but a STRUCTURED
# form so prose mentioning "owner:" is never mistaken for a marker: a section
# uses an HTML comment under the heading; a symbol uses a full `owner:` line.
_SECTION_OWNER_RE = re.compile(r"<!--\s*owner:\s*([A-Za-z0-9._@-]+)\s*-->")
_SYMBOL_OWNER_RE = re.compile(r"(?m)^\s*owner:\s*([A-Za-z0-9._@-]+)\s*$")
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,})\b")        # AXI, DMA, RAG, ...
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
    "not", "but", "you", "your", "use", "used", "uses", "via", "per", "its",
    "all", "any", "one", "two", "how", "what", "when", "where", "which", "who",
    "doc", "docs", "file", "files", "code", "line", "lines", "see", "etc",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "node"


def _path_id(rel: str) -> str:
    """Path-derived id that PRESERVES separators, so distinct paths never collide
    (e.g. 'a/b.md' -> 'a/b-md' vs 'a-b.md' -> 'a-b-md'). _slug alone is not
    injective because it maps '/', '-' and '.' all to '-'."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    return "/".join(_slug(p) for p in parts) or "node"


def _rel(path: str, root: str) -> str:
    return os.path.relpath(path, root)


def _walk(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # Sort dirnames so traversal order (hence cross-dir symlink dedup) is
        # deterministic across hosts/filesystems, not os.walk-entry-order.
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        yield dirpath, dirnames, filenames


def _real_owner(value):
    """A frontmatter/marker owner counts only if present and not the TBD placeholder."""
    if value and value != "TBD":
        return value
    return None


def _keywords(*texts: str) -> list:
    """Lowercased significant words + preserved ACRONYMS, deduped, capped."""
    out = []
    seen = set()
    for t in texts:
        for ac in _ACRONYM_RE.findall(t or ""):
            if ac not in seen:
                seen.add(ac)
                out.append(ac)
    for t in texts:
        for w in _WORD_RE.findall((t or "").lower()):
            # skip stopwords, already-seen words, and the lowercase form of an
            # acronym we already emitted in cased form (AXI -> don't re-add axi).
            if w in _STOP or w in seen or w.upper() in seen:
                continue
            seen.add(w)
            out.append(w)
    return out[:12]


def _parse_frontmatter(text: str):
    """Return (frontmatter dict or None, body string after the closing ---)."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    data = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        line = lines[i]
        if line[:1] in (" ", "\t"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return data, "\n".join(lines[body_start:])


def _parse_tags(raw) -> list:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [t.strip() for t in raw.split(",") if t.strip()]


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    m = re.search(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:240]


def _docstring_meta(doc: str):
    """Module docstrings in this repo carry title:/summary:/owner: lines."""
    meta = {}
    first = ""
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        if ":" in s and s.split(":", 1)[0] in (
                "title", "summary", "layer", "public_api", "owner", "visibility"):
            k, _, v = s.partition(":")
            meta[k.strip()] = v.strip()
        elif not first:
            first = s
    return meta, first


# --------------------------------------------------------------------------- #
# node builders
# --------------------------------------------------------------------------- #
def _doc_and_sections(path: str, root: str, nodes: list):
    rel = _rel(path, root)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return
    fm, body = _parse_frontmatter(text)
    if fm is None:
        return  # only frontmatter-bearing markdown is a corpus doc
    doc_id = fm.get("id") or _path_id(rel)
    doc_owner = _real_owner(fm.get("owner"))
    visibility = fm.get("visibility") or "internal"
    title = fm.get("title") or rel
    summary = fm.get("summary") or ""
    tags = _parse_tags(fm.get("tags")) + _keywords(title, summary)
    nodes.append({
        "node_id": doc_id,
        "kind": "doc",
        "title": title,
        "path": rel,
        "anchor": None,
        "lineno": None,
        "summary": summary,
        "summary_source": "authored" if summary else "",
        "text_excerpt": " ".join(body.split())[:400],
        "owner": doc_owner or "",
        "owner_source": "frontmatter" if doc_owner else "none",
        "owner_origin": rel if doc_owner else None,
        "tags": sorted(set(tags)),
        "visibility": visibility,
        "updated": fm.get("updated") or "",
        "parent": None,
        "children": [],
        "links": [],
    })
    _sections(body, doc_id, rel, doc_owner, visibility, nodes)


def _sections(body, doc_id, rel, doc_owner, doc_visibility, nodes):
    lines = body.splitlines()
    blocks = []
    cur = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            if cur:
                blocks.append(cur)
            cur = {"level": len(m.group(1)), "title": m.group(2),
                   "lineno": i + 1, "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur:
        blocks.append(cur)

    last_h2 = None
    seen_anchors = {}
    for b in blocks:
        base = _slug(b["title"])
        # disambiguate repeated heading slugs within one doc (Setup, setup-2, ...)
        n = seen_anchors.get(base, 0) + 1
        seen_anchors[base] = n
        anchor = base if n == 1 else "%s-%d" % (base, n)
        sec_id = "%s#%s" % (doc_id, anchor)
        btext = "\n".join(b["body"])
        marker = _SECTION_OWNER_RE.search("\n".join(b["body"][:3]))
        marker_owner = _real_owner(marker.group(1)) if marker else None
        if marker_owner:
            owner, osrc, oorigin = marker_owner, "marker", "%s#%s" % (rel, anchor)
        elif doc_owner:
            owner, osrc, oorigin = doc_owner, "inherited", rel
        else:
            owner, osrc, oorigin = "", "none", None
        parent = doc_id if b["level"] == 2 else (last_h2 or doc_id)
        if b["level"] == 2:
            last_h2 = sec_id
        summ = _first_sentence(btext)
        nodes.append({
            "node_id": sec_id,
            "kind": "section",
            "title": b["title"],
            "path": rel,
            "anchor": anchor,
            "lineno": b["lineno"],
            "summary": summ,
            "summary_source": "authored" if summ else "",
            "text_excerpt": " ".join(btext.split())[:400],
            "owner": owner,
            "owner_source": osrc,
            "owner_origin": oorigin,
            "tags": sorted(set(_keywords(b["title"], btext))),
            "visibility": doc_visibility,   # inherit the doc's visibility (no leaks)
            "updated": "",
            "parent": parent,
            "children": [],
            "links": [],
        })


def _nearest_readme(dirpath: str, root: str):
    """Walk up to the repo root for a README.md; return (owner, origin, visibility)."""
    d = dirpath
    while True:
        readme = os.path.join(d, "README.md")
        if os.path.isfile(readme):
            try:
                with open(readme, encoding="utf-8") as fh:
                    fm, _ = _parse_frontmatter(fh.read())
            except Exception:
                fm = None
            fm = fm or {}
            owner = _real_owner(fm.get("owner"))
            if owner or fm.get("visibility"):
                return owner, _rel(readme, root), fm.get("visibility")
        if os.path.abspath(d) == os.path.abspath(root):
            return None, None, None
        parent = os.path.dirname(d)
        if parent == d:
            return None, None, None
        d = parent


def _module_and_symbols(path: str, root: str, nodes: list):
    rel = _rel(path, root)
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src, filename=path)
    except Exception:
        return
    doc = ast.get_docstring(tree)
    if not doc:
        return  # only documented modules are corpus nodes
    meta, first = _docstring_meta(doc)
    mod_id = _path_id(rel)
    title = meta.get("title") or rel
    summary = meta.get("summary") or first
    # owner + visibility: own docstring owner is the module's "frontmatter"; else
    # inherit the nearest package README (owner_source 'inherited').
    nr_owner, nr_origin, nr_vis = _nearest_readme(os.path.dirname(path), root)
    mod_owner = _real_owner(meta.get("owner"))
    if mod_owner:
        osrc, oorigin = "frontmatter", rel
    elif nr_owner:
        mod_owner, osrc, oorigin = nr_owner, "inherited", nr_origin
    else:
        osrc, oorigin = "none", None
    visibility = meta.get("visibility") or nr_vis or "internal"
    nodes.append({
        "node_id": mod_id,
        "kind": "module",
        "title": title,
        "path": rel,
        "anchor": None,
        "lineno": 1,
        "summary": summary,
        "summary_source": "authored" if summary else "",
        "text_excerpt": " ".join(doc.split())[:400],
        "owner": mod_owner or "",
        "owner_source": osrc,
        "owner_origin": oorigin,
        "tags": sorted(set(_keywords(title, summary))),
        "visibility": visibility,
        "updated": "",
        "parent": None,
        "children": [],
        "links": [],
    })
    exported = _exported_names(tree)
    defs = {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for name in sorted(exported):
        nd = defs.get(name)
        if nd is None:
            continue  # re-exported from elsewhere; indexed where it is defined
        sdoc = ast.get_docstring(nd) or ""
        marker = _SYMBOL_OWNER_RE.search(sdoc)
        marker_owner = _real_owner(marker.group(1)) if marker else None
        if marker_owner:
            owner, so, oo = marker_owner, "marker", "%s::%s" % (rel, name)
        elif mod_owner:
            owner, so, oo = mod_owner, "inherited", oorigin
        else:
            owner, so, oo = "", "none", None
        summ = _first_sentence(sdoc)
        nodes.append({
            "node_id": "%s::%s" % (mod_id, name),
            "kind": "symbol",
            "title": name,
            "path": rel,
            "anchor": name,
            "lineno": getattr(nd, "lineno", None),
            "summary": summ,
            "summary_source": "authored" if summ else "",
            "text_excerpt": " ".join(sdoc.split())[:400],
            "owner": owner,
            "owner_source": so,
            "owner_origin": oo,
            "tags": sorted(set(_keywords(name, summ))),
            "visibility": visibility,       # symbols inherit the module's visibility
            "updated": "",
            "parent": mod_id,
            "children": [],
            "links": [],
        })


def _exported_names(tree) -> list:
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" \
                        and isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        val = getattr(elt, "s", None)
                        if val is None and isinstance(elt, ast.Constant):
                            val = elt.value
                        if isinstance(val, str):
                            out.append(val)
    return out


def build_corpus(root: str) -> dict:
    """Walk the repo and return the corpus dict (nodes + tree edges, no links).

    Pure + deterministic: authored docstrings/frontmatter become canonical
    summaries; nodes with none are emitted with summary_source == "" (a gap the
    index_enforcer fills later, marking it "generated"). No model is ever called.
    """
    nodes = []
    seen_real = set()
    for dirpath, _, filenames in _walk(root):
        top = _rel(dirpath, root).split(os.sep)[0]
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            real = os.path.realpath(full)
            if f.endswith(".md"):
                # Any frontmatter-bearing markdown is a corpus doc (the "one
                # brain" ingests every labeled doc, not just README/AGENT). The
                # realpath dedup collapses the CLAUDE.md -> AGENT.md symlink.
                if real in seen_real:
                    continue
                seen_real.add(real)
                _doc_and_sections(full, root, nodes)
            elif f.endswith(".py") and top in CODE_ROOTS:
                _module_and_symbols(full, root, nodes)

    # denormalize children from parent edges
    by_id = {n["node_id"]: n for n in nodes}
    for n in nodes:
        p = n["parent"]
        if p and p in by_id:
            by_id[p]["children"].append(n["node_id"])
    for n in nodes:
        n["children"].sort()
    nodes.sort(key=lambda n: n["node_id"])
    return {"schema_version": SCHEMA_VERSION, "root": ".", "nodes": nodes}


def _duplicate_ids(nodes):
    seen, dups = set(), set()
    for n in nodes:
        nid = n["node_id"]
        if nid in seen:
            dups.add(nid)
        seen.add(nid)
    return sorted(dups)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build wiki/corpus.json from the repo (deterministic).")
    ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
    ap.add_argument("--out", default=os.path.join("wiki", "corpus.json"),
                    help="output path (default: wiki/corpus.json)")
    args = ap.parse_args(argv)
    corpus = build_corpus(args.root)
    dups = _duplicate_ids(corpus["nodes"])
    if dups:   # node_id is the corpus primary key — fail loudly, never silently collapse
        sys.stderr.write("ERROR build_corpus: duplicate node_id(s): %s\n" % dups)
        return 1
    out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2, sort_keys=True)
        fh.write("\n")
    gaps = sum(1 for n in corpus["nodes"] if not n["summary_source"])
    unowned = sum(1 for n in corpus["nodes"] if n["owner_source"] == "none")
    print("wrote %s: %d nodes (%d summary gaps, %d unowned)"
          % (_rel(out, args.root), len(corpus["nodes"]), gaps, unowned))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_LINK_CORPUS_SRC = r'''
#!/usr/bin/env python3
"""
title: Link corpus job
kind: script
layer: n/a
summary: Deterministic: add keyword/entity link edges to wiki/corpus.json in place.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")


def link_corpus(corpus: dict, max_links: int = 8, min_score: float = 0.12) -> dict:
    """Add deterministic keyword/entity link edges (returns the same corpus).

    Two nodes link when they share tags/entities (e.g. both mention "AXI").
    Edges carry the shared token in `via` and a Jaccard `score`, with
    source="deterministic" so an LLM-added semantic edge stays distinguishable.
    Idempotent: existing edges are recomputed from scratch each run.
    """
    nodes = corpus.get("nodes", [])
    tagsets = {n["node_id"]: set(n.get("tags", [])) for n in nodes}
    # invert: tag -> node_ids that carry it
    by_tag = {}
    for nid, tags in tagsets.items():
        for t in tags:
            by_tag.setdefault(t, set()).add(nid)
    for n in nodes:
        nid = n["node_id"]
        mine = tagsets[nid]
        if not mine:
            n["links"] = []
            continue
        candidates = set()
        for t in mine:
            candidates |= by_tag.get(t, set())
        candidates.discard(nid)
        scored = []
        for other in candidates:
            theirs = tagsets[other]
            shared = mine & theirs
            if not shared:
                continue
            score = len(shared) / float(len(mine | theirs))
            if score < min_score:
                continue
            via = sorted(shared)[0]
            scored.append((round(score, 4), via, other))
        # strongest first, then stable by (via, node_id)
        scored.sort(key=lambda s: (-s[0], s[1], s[2]))
        n["links"] = [
            {"to": other, "via": via, "score": score,
             "kind": "keyword", "source": "deterministic"}
            for (score, via, other) in scored[:max_links]
        ]
    return corpus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Add link edges to wiki/corpus.json (deterministic, in place).")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, help="corpus path (default: wiki/corpus.json)")
    ap.add_argument("--max-links", type=int, default=8, help="max edges per node")
    args = ap.parse_args(argv)
    path = args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    if not os.path.exists(path):
        print("no corpus at %s; run build_corpus.py first (skipping)." % args.corpus)
        return 0
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    link_corpus(corpus, max_links=args.max_links)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2, sort_keys=True)
        fh.write("\n")
    edges = sum(len(n.get("links", [])) for n in corpus.get("nodes", []))
    print("linked %s: %d edges across %d nodes"
          % (args.corpus, edges, len(corpus.get("nodes", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_QUERY_CORPUS_SRC = r'''
#!/usr/bin/env python3
"""
title: Query corpus
kind: script
layer: n/a
summary: Read-only retrieval over wiki/corpus.json — the wiki_navigator's tool.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")


def _tokens(text: str) -> set:
    out = set()
    for w in _WORD_RE.findall(text or ""):
        out.add(w.lower())
        if w.isupper():
            out.add(w)        # keep acronyms (AXI) matchable verbatim
    return out


def query(corpus: dict, question: str, max_nodes: int = 8) -> list:
    """Return up to max_nodes candidate nodes for the question, best first.

    Deterministic retrieval: score each node by query-token overlap with its
    tags/title/summary, then pull in each hit's parent and linked nodes so the
    caller gets a connected neighbourhood (tree + links) to reason over.
    """
    nodes = {n["node_id"]: n for n in corpus.get("nodes", [])}
    q = _tokens(question)
    if not q:
        return []
    scored = []
    for nid, n in nodes.items():
        hay = set(t.lower() for t in n.get("tags", [])) | _tokens(n.get("title", "")) \
            | _tokens(n.get("summary", ""))
        overlap = len(q & hay)
        if overlap:
            scored.append((overlap, nid))
    scored.sort(key=lambda s: (-s[0], s[1]))
    chosen, order = set(), []
    # Pass 1: guarantee every genuine keyword hit (best-first) before any filler.
    for _, nid in scored:
        if len(order) >= max_nodes:
            break
        if nid not in chosen:
            chosen.add(nid)
            order.append(nid)
    # Pass 2: expand the neighbourhood (parent + links) to fill the remainder,
    # so a top hit's zero-overlap neighbours never starve a real lower-ranked hit.
    for _, nid in scored:
        if len(order) >= max_nodes:
            break
        for related in [nodes[nid].get("parent")] + \
                [e["to"] for e in nodes[nid].get("links", [])]:
            if related and related in nodes and related not in chosen:
                chosen.add(related)
                order.append(related)
                if len(order) >= max_nodes:
                    break
    return [nodes[nid] for nid in order[:max_nodes]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only retrieval over wiki/corpus.json.")
    ap.add_argument("question", help="the question / keywords to retrieve for")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, help="corpus path (default: wiki/corpus.json)")
    ap.add_argument("--max-nodes", type=int, default=8, help="max candidate nodes")
    args = ap.parse_args(argv)
    path = args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    if not os.path.exists(path):
        print("[]")  # graceful: empty retrieval when no corpus yet
        return 0
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    hits = query(corpus, args.question, max_nodes=args.max_nodes)
    json.dump(hits, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_ACCOUNTABILITY_SRC = r'''
#!/usr/bin/env python3
"""
title: Accountability report
kind: script
layer: n/a
summary: Read-only: list corpus nodes with no resolved owner (the accountability gaps).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")


def unowned(corpus: dict) -> list:
    """Return nodes whose owner could not be resolved (owner_source == 'none')."""
    return [n for n in corpus.get("nodes", []) if n.get("owner_source") == "none"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Report corpus nodes with no resolved owner.")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, help="corpus path (default: wiki/corpus.json)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)
    path = args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    if not os.path.exists(path):
        print("no corpus at %s; run build_corpus.py first." % args.corpus)
        return 0
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    gaps = unowned(corpus)
    if args.json:
        json.dump([{"node_id": n["node_id"], "kind": n["kind"], "path": n["path"]}
                   for n in gaps], sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    total = len(corpus.get("nodes", []))
    print("accountability: %d of %d nodes have no resolved owner" % (len(gaps), total))
    for n in sorted(gaps, key=lambda n: n["node_id"]):
        print("  %-9s %s  (%s)" % (n["kind"], n["node_id"], n["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_TOOL_SPECS = [
    ('structure_check', r'''
---
title: Structure check
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/check_structure.py
tags: [tool, enforce, structure]
summary: Validate repo structure + frontmatter against CONVENTIONS.md; read-only.
id: tool-structure-check
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/check_structure.py
tool_effect: read-only
---

# Structure check

## Command
`python3 scripts/check_structure.py`

## Purpose
Enforces CONVENTIONS.md: frontmatter validity, unique corpus ids, documented
dirs, the `__init__.py` package boundary, the private-import boundary, plus the
authored-coverage and tool-spec/accountability warnings. This is how the
`index_enforcer` proves the repo is convention-clean before it trusts the corpus.

## When to use
- Before building/refreshing the corpus (a dirty tree yields a dirty index).
- After any structural edit (new dir, package, moved file).
- NOT for content/meaning questions — it checks structure, not semantics.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| (none) | — | — | Scans the repo root; no flags. |

## Output
`WARN <msg>` / `ERROR <msg>` lines on stdout, then
`check_structure: N error(s), M warning(s)`. Exit 0 = clean, 1 = errors.
Warnings never change the exit code.

## Side effects
READ-ONLY. Reads files; writes nothing; safe to run any number of times.

## Used by
- agents/index_enforcer
'''),
    ('build_corpus', r'''
---
title: Build corpus
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/jobs/build_corpus.py
tags: [tool, corpus, index, AXI]
summary: Walk the repo into wiki/corpus.json (doc/module/section/symbol nodes); writes.
id: tool-build-corpus
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/jobs/build_corpus.py --out wiki/corpus.json
tool_effect: writes
---

# Build corpus

## Command
`python3 scripts/jobs/build_corpus.py [--root DIR] [--out PATH]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
Deterministically extracts the one-brain index: every frontmatter doc, code
module, doc section, and `__all__` symbol becomes a node with its AUTHORED
summary (frontmatter/docstring), tree edges (parent/children), tags, resolved
owner, and provenance. Nodes lacking an authored summary are emitted as gaps
(`summary_source: ""`) for the agent to fill — it never invents prose itself.

## When to use
- To (re)build the corpus after `structure_check` passes.
- NOT for retrieval (that is `query_corpus`) and NOT to fill gaps (that is the
  agent's model step).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--root` | no | repo root | tree to index |
| `--out` | no | `wiki/corpus.json` | output path |

## Output
Writes `wiki/corpus.json` (`{schema_version, root, nodes:[...]}`); prints a
node/gap/unowned count. Exit non-zero on failure.

## Side effects
WRITES `wiki/corpus.json` (generated, gitignored — a view, never a source).
Deterministic + idempotent: same tree → same file. No model call.

## Used by
- agents/index_enforcer
'''),
    ('link_corpus', r'''
---
title: Link corpus
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/jobs/link_corpus.py
tags: [tool, corpus, links, entity, AXI]
summary: Add deterministic keyword/entity link edges to wiki/corpus.json in place; writes.
id: tool-link-corpus
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/jobs/link_corpus.py --corpus wiki/corpus.json
tool_effect: writes
---

# Link corpus

## Command
`python3 scripts/jobs/link_corpus.py [--corpus PATH] [--max-links N]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
Adds the cross-references that make the corpus a graph, not just a tree: two
nodes that share entities/keywords (e.g. both mention "AXI") get a link edge
carrying the shared token (`via`) and a Jaccard `score`, with
`source: deterministic`. The agent may later add richer `semantic` edges
(`source: generated`) — kept distinguishable so a reviewer can distrust them.

## When to use
- Right after `build_corpus`, before the navigator answers.
- NOT to create the nodes (that is `build_corpus`).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--corpus` | no | `wiki/corpus.json` | corpus to augment |
| `--max-links` | no | 8 | max edges per node |

## Output
Rewrites the `links` of every node in place; prints an edge/node count.
No corpus present → prints a notice and exits 0.

## Side effects
WRITES `wiki/corpus.json` (in place). Deterministic + idempotent: re-running
recomputes the same edges. No model call.

## Used by
- agents/index_enforcer
'''),
    ('query_corpus', r'''
---
title: Query corpus
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/query_corpus.py
tags: [tool, corpus, retrieval, query]
summary: Read-only retrieval over wiki/corpus.json — candidate nodes for a question.
id: tool-query-corpus
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/query_corpus.py "QUESTION" --corpus wiki/corpus.json
tool_effect: read-only
---

# Query corpus

## Command
`python3 scripts/query_corpus.py "QUESTION" [--corpus PATH] [--max-nodes N]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The `wiki_navigator`'s retrieval step: scores nodes by query-token overlap with
their tags/title/summary, then pulls in each hit's parent and linked nodes so
the caller receives a connected tree+link neighbourhood to reason over. Each
node carries `summary_source` and `owner`/`owner_source` so the answer can cite
provenance and accountability.

## When to use
- To gather candidate context before synthesizing an answer.
- NOT to build or mutate the corpus.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `QUESTION` | yes | — | the question / keywords |
| `--corpus` | no | `wiki/corpus.json` | corpus to read |
| `--max-nodes` | no | 8 | retrieval budget |

## Output
A JSON array of node objects on stdout, best match first. No corpus present →
prints `[]` and exits 0.

## Side effects
READ-ONLY. Reads the corpus; writes nothing; no model call (retrieval is
deterministic — the model step is the agent's, not this tool's).

## Used by
- agents/wiki_navigator
'''),
    ('accountability_report', r'''
---
title: Accountability report
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/accountability_report.py
tags: [tool, accountability, owner, governance]
summary: Read-only list of corpus nodes with no resolved owner (accountability gaps).
id: tool-accountability-report
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/accountability_report.py --corpus wiki/corpus.json
tool_effect: read-only
---

# Accountability report

## Command
`python3 scripts/accountability_report.py [--corpus PATH] [--json]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
Lists every corpus node whose owner could not be resolved
(`owner_source: none`) — the human-accountability gaps. A node inherits its
owner from a section/symbol marker, then frontmatter, then its parent; only
nodes that resolve to nothing (or to the `TBD` placeholder) are reported.

## When to use
- When the `index_enforcer` reports owner gaps, to enumerate exactly which
  docs/sections/symbols need an owner assigned.
- In CI/review to keep accountability from rotting.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--corpus` | no | `wiki/corpus.json` | corpus to read |
| `--json` | no | off | emit JSON instead of text |

## Output
A count plus one line per unowned node (`kind  node_id  (path)`), or JSON with
`--json`. No corpus present → prints a notice and exits 0.

## Side effects
READ-ONLY. Reads the corpus; writes nothing; no model call.

## Used by
- agents/index_enforcer
'''),
]


_WIKI_AGENT_DIRS = [
    {
        "dir": 'agents/index_enforcer',
        "title": 'Index enforcer',
        "tags": ['agent', 'enforcer', 'index', 'corpus'],
        "summary": 'Enforces conventions and builds/maintains the accountable wiki corpus.',
        "readme_body": r'''
An example agent that is both **enforcer** and **indexer**. It gates the repo
with the `structure_check` tool, (re)builds the wiki corpus with `build_corpus`
+ `link_corpus`, flags human-accountability gaps with `accountability_report`,
and fills *missing* summaries via `models/` -- never overwriting authored ones.

It is thin: policy + prompt only. The real work lives in `scripts/`, invoked as
**tools** (per the specs in `agents/tools/`, declared in `tools.md`); the model
comes from `models/`. The single public symbol is `enforce(...)`, returning an
`EnforceReport`. It **defaults to dry-run**: `enforce()` reports the plan + gaps
and writes nothing; `enforce(execute=True)` runs the deterministic build/link;
gap-fill additionally needs `fix_gaps=True`.
''',
        "rules": ['Policy/prompt only. Invoke `scripts/` doers as **tools** via their CLI (per `agents/tools/` specs in `tools.md`); never `import` script logic.', 'Get the model from `models/` (`get_model`); never name a provider. Keep prompt/policy in `_brain.py` private behind `__init__.py`; `enforce` is the only public symbol.', 'Default to dry-run (`execute=False`): no writes, no model calls. Build/link need `execute=True`; gap-fill additionally needs `fix_gaps=True`.', 'Control flow is a neutral `Plan` (steps + edges; see `runtimes/`) executed by a `Runtime` — the dry-run effect-guard (`writes`/`model-call` steps are skipped unless `execute=True`) lives in the runtime, not in inline `if`s. `enforce(runtime=...)` selects the engine; default is the stdlib `inprocess` engine, never a vendor.', 'The fill loop is **durable**: one gap per step, recomputed from the corpus (idempotent), so a crash mid-fill (an EDR SIGKILL) resumes via the checkpointer and already-filled gaps are not re-run. `enforce` defaults to a `FileCheckpointer` under `wiki/.runtime` and auto-resumes a leftover snapshot.', 'Authored summaries and owners are canonical -- generation is a fallback for gaps only, and is always marked `generated`.'],
        "init": r'''
"""
title: Index enforcer agent
layer: backend
public_api: yes
summary: Enforces conventions, builds/maintains the wiki corpus, flags owner gaps.
"""
from ._brain import EnforceReport, enforce

__all__ = ["enforce", "EnforceReport"]
''',
        "brain": r'''
"""
title: Index enforcer brain
layer: backend
public_api: no
summary: Plan: gate -> build -> link -> report -> (durable fill loop) -> commit; run on a neutral Runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from models import get_model
from runtimes import (
    END,
    MODEL_CALL,
    READ_ONLY,
    WRITES,
    Edge,
    FileCheckpointer,
    Plan,
    Step,
    get_runtime,
)

__all__ = ["enforce", "EnforceReport"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_CKPT_DIR = os.path.join("wiki", ".runtime")   # gitignored; durable fill snapshots


@dataclass(frozen=True)
class EnforceReport:
    """Convention + coverage + accountability gaps found while indexing."""
    structure_errors: tuple
    structure_warnings: tuple
    corpus_path: str
    nodes: int
    summary_gaps: tuple
    owner_gaps: tuple
    gaps_filled: int
    dry_run: bool


def _run(args):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported).

    Uses the SAME interpreter running this agent (sys.executable), so the tools
    run under a compatible Python rather than a hardcoded 'python3' on PATH.
    """
    proc = subprocess.run([sys.executable] + args, cwd=_REPO,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _load_corpus(root):
    path = os.path.join(root, _CORPUS)
    if not os.path.exists(path):
        return {"nodes": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _system_prompt():
    with open(os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8") as fh:
        return fh.read()


def _gap_prompt(node):
    return (_system_prompt()
            + "\n\n# Task\nWrite ONE plain sentence summarizing the node below, "
            "using only its own text. Output the sentence and nothing else.\n\n"
            "title: %s\npath: %s\n---\n%s\n"
            % (node.get("title", ""), node.get("path", ""), node.get("text_excerpt", "")))


def _ungapped(corpus):
    """Nodes still missing a summary_source, in corpus order (the fill work-list)."""
    return [n for n in corpus.get("nodes", []) if not n.get("summary_source")]


# --- plan steps: each returns a dict merged into the run state -----------------
# Deterministic logic stays in pure-stdlib scripts/ doers invoked as CLIs; these
# steps orchestrate them. The model is reached only in the one MODEL_CALL step,
# so the runtime skips it (and the WRITES steps) unless execute=True.

def _gate(state):
    """Read-only: run check_structure and capture its errors/warnings."""
    _, out, _ = _run(["scripts/check_structure.py"])
    return {
        "s_errors": tuple(ln[6:] for ln in out.splitlines() if ln.startswith("ERROR ")),
        "s_warnings": tuple(ln[6:].strip() for ln in out.splitlines() if ln.startswith("WARN  ")),
    }


def _build(state):
    """Writes: (re)build the wiki corpus tree."""
    _run(["scripts/jobs/build_corpus.py", "--out", _CORPUS])
    return None


def _link(state):
    """Writes: add deterministic entity/keyword link edges to the corpus."""
    _run(["scripts/jobs/link_corpus.py", "--corpus", _CORPUS])
    return None


def _report(state):
    """Read-only: enumerate summary gaps (no authored summary) and owner gaps."""
    corpus = _load_corpus(state["root"])
    nodes = corpus.get("nodes", [])
    summary_gaps = tuple(n["node_id"] for n in _ungapped(corpus))
    # Owner gaps come from the declared accountability_report tool (its CLI),
    # not a re-implemented predicate here -- read-only, so safe in dry-run too.
    _, ar_out, _ = _run(["scripts/accountability_report.py", "--corpus", _CORPUS, "--json"])
    try:
        owner_gaps = tuple(n["node_id"] for n in json.loads(ar_out)) if ar_out.strip() else ()
    except ValueError:
        owner_gaps = ()   # no corpus yet (tool prints a notice, not JSON)
    return {"corpus": corpus, "nodes": nodes,
            "summary_gaps": summary_gaps, "owner_gaps": owner_gaps, "gaps_filled": 0}


def _fill_one(state):
    """Model-call: fill the NEXT single missing summary, in memory.

    One gap per step (not the whole loop) so the runtime checkpoints after each
    fill -- a crash mid-fill (e.g. an EDR SIGKILL) resumes at the cursor and the
    already-filled gaps are not recomputed. The work-list is recomputed from the
    corpus each call, so it is idempotent and resume-safe. Authored summaries are
    never touched (only nodes lacking summary_source are filled).
    """
    corpus = state["corpus"]
    todo = _ungapped(corpus)
    if not todo:
        return {}
    node = todo[0]
    node["summary"] = get_model(state.get("model")).run(_gap_prompt(node)).strip()
    node["summary_source"] = "generated"   # never "authored"
    return {"corpus": corpus, "gaps_filled": state.get("gaps_filled", 0) + 1}


def _commit(state):
    """Writes: persist the corpus once, deterministically (sorted keys)."""
    with open(os.path.join(state["root"], _CORPUS), "w", encoding="utf-8") as fh:
        json.dump(state["corpus"], fh, indent=2, sort_keys=True)
        fh.write("\n")
    return None


# --- the plan: control flow as data, with a durable fill loop ------------------
# The clauses that used to be inline `if execute and ... and not s_errors` are
# now named edge predicates. `execute` is the runtime's job for the dry-run guard
# AND a domain-state key so the loop predicate is engine-neutral (the runtime's
# internal flag isn't visible to edge predicates).

def _clean(state):
    """True when the structure gate found no errors."""
    return not state.get("s_errors")


def _wants_fill(state):
    """True when gap-fill is requested and there is a clean tree with gaps."""
    return bool(state.get("fix_gaps")) and bool(_ungapped(state.get("corpus", {}))) \
        and not state.get("s_errors")


def _more_to_fill(state):
    """True when authorized to fill and at least one gap remains (loop guard)."""
    return bool(state.get("execute")) and bool(_ungapped(state.get("corpus", {})))


_PLAN = Plan(
    name="index_enforce",
    entry="gate",
    steps=(
        Step("gate", READ_ONLY, _gate),
        Step("build", WRITES, _build),
        Step("link", WRITES, _link),
        Step("report", READ_ONLY, _report),
        Step("fill", MODEL_CALL, _fill_one),
        Step("commit", WRITES, _commit),
    ),
    edges=(
        Edge("gate", "build", when=_clean),    # clean tree -> rebuild
        Edge("gate", "report"),                # dirty tree -> straight to report
        Edge("build", "link"),
        Edge("link", "report"),
        Edge("report", "fill", when=_wants_fill),
        Edge("report", END),
        Edge("fill", "fill", when=_more_to_fill),   # durable loop: one gap per step
        Edge("fill", "commit"),
        Edge("commit", END),
    ),
)


def enforce(*, execute=False, fix_gaps=False, model=None, root=None, runtime=None,
            checkpointer=None, run_key="index_enforce"):
    """Gate -> build_corpus -> link_corpus -> report -> durable fill loop -> commit.

    The pipeline is a neutral ``Plan`` executed by a ``Runtime`` (default the
    pure-stdlib ``inprocess`` engine; ``runtime="langgraph"`` runs the same plan
    on LangGraph). WRITES and the model-backed fill run only when ``execute=True``
    (dry-run default); the fill additionally needs ``fix_gaps=True``.

    When actually filling, the fill loop is made **durable**: each gap is its own
    step, so the runtime snapshots after every fill and a crash mid-fill (an EDR
    SIGKILL, say) **resumes** instead of re-running model calls. By default a
    ``FileCheckpointer`` is used under ``wiki/.runtime`` and a leftover snapshot
    (from a prior crash) is auto-resumed; pass your own ``checkpointer`` to
    override. The model comes via ``models.get_model(model)`` -- never a provider.
    """
    root = root or _REPO
    if checkpointer is None and execute and fix_gaps:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {"root": root, "model": model, "fix_gaps": fix_gaps, "execute": execute}
    kwargs = {"execute": execute}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["run_key"] = run_key
        if checkpointer.load(run_key) is not None:   # a prior run crashed -> resume
            kwargs["resume"] = None
    st = get_runtime(runtime).run(_PLAN, init, **kwargs).state
    return EnforceReport(
        structure_errors=st.get("s_errors", ()),
        structure_warnings=st.get("s_warnings", ()),
        corpus_path=_CORPUS,
        nodes=len(st.get("nodes", [])),
        summary_gaps=st.get("summary_gaps", ()),
        owner_gaps=st.get("owner_gaps", ()),
        gaps_filled=st.get("gaps_filled", 0),
        dry_run=not execute,
    )
''',
        "prompt": r'''
# Role
You are the **index enforcer**. You keep the repository convention-clean and the
wiki corpus current, linked, and accountable. You are a curator, not an author —
authored summaries and owners are canonical and you never overwrite them.

# Inputs
- The repository tree.
- The wiki corpus at `wiki/corpus.json` (once built).

# Tools
Your permitted tools are listed in `tools.md`. Invoke each one per its spec in
`agents/tools/`. Never invoke a tool that is not in `tools.md`.

# Procedure
1. Run **structure_check**. If it reports errors, STOP and surface them — a dirty
   tree yields a dirty index.
2. Run **build_corpus**, then **link_corpus**, to (re)extract nodes and add
   entity/keyword edges.
3. Run **accountability_report** to enumerate nodes with no resolved owner.
4. For summary gaps (`summary_source` empty), draft ONE sentence from the node's
   own text only, and mark it `generated`. NEVER touch an authored summary.

# Output contract
Return an `EnforceReport`: `structure_errors`, `structure_warnings`, `nodes`,
`summary_gaps`, `owner_gaps`, `gaps_filled`, `dry_run`.

# Safety
- Default to **dry-run** (`execute=False`): describe what you WOULD do; make no
  writes and no model calls. The read-only gate still runs so the report is real.
- Build/link are deterministic writes (`execute=True`).
- Gap-fill calls a model and additionally requires `fix_gaps=True`.
- The model comes from `models/`; never name a provider.
''',
        "tools": r'''
---
title: index_enforcer — toolset
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: [agent, toolset, manifest]
summary: The shared tools agents/index_enforcer is permitted to invoke.
id: agents-index-enforcer-tools
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# index_enforcer — toolset

This agent may invoke ONLY the tools below. Each row points at a shared spec in
`agents/tools/`. Adding a tool = add a row here AND add this agent to that
spec's `## Used by` (the binding is bidirectional).

| Tool spec | Effect | Used for |
|-----------|--------|----------|
| `../tools/structure_check.tool.md` | read-only | gate the repo before indexing |
| `../tools/build_corpus.tool.md` | writes | (re)build the wiki corpus tree |
| `../tools/link_corpus.tool.md` | writes | add deterministic entity/keyword links |
| `../tools/accountability_report.tool.md` | read-only | enumerate owner gaps to flag |
''',
    },

    {
        "dir": 'agents/wiki_navigator',
        "title": 'Wiki navigator',
        "tags": ['agent', 'wiki', 'retrieval', 'qa'],
        "summary": 'Answers questions from the wiki corpus with citations and provenance.',
        "readme_body": r'''
An example agent that answers a question by traversing the wiki corpus the
`index_enforcer` built. It retrieves a connected neighbourhood of nodes (tree +
entity/keyword links) with the read-only `query_corpus` tool, then synthesizes
an answer via `models/` -- citing every source.

It is thin: policy + prompt only. The single public symbol is `answer(...)`,
returning an `Answer` whose `citations` carry each source's `summary_source`
(authored vs generated) and `owner`/`owner_source`, so a reader can weight trust
and see accountability. It **defaults to dry-run**: retrieval always runs (so
`citations` is populated), but `answer(question)` returns the prompt it *would*
send; pass `execute=True` to call the model. It never surfaces
`confidential`/`restricted` nodes.
''',
        "rules": ['Policy/prompt only. Retrieve via the `query_corpus` tool (its CLI, per `agents/tools/`); never `import` script logic. `answer` is the only public symbol; keep policy in `_brain.py`.', 'Get the model from `models/` (`get_model`); never name a provider.', 'Default to dry-run (`execute=False`): retrieval + citations run, but no model call.', 'Control flow is a neutral `Plan` (`retrieve` -> `synthesize`; see `runtimes/`) executed by a `Runtime`; only the `synthesize` (`model-call`) step is gated by `execute`. `answer(runtime=...)` selects the engine; default is the stdlib `inprocess` engine, never a vendor.', 'Answer only from retrieved nodes; cite every claim by `node_id`; surface provenance (authored vs generated) and accountability (`owner_source`); never reveal `confidential`/`restricted` nodes.'],
        "init": r'''
"""
title: Wiki navigator agent
layer: backend
public_api: yes
summary: Answers a question by traversing the corpus tree+links; cited answer + provenance.
"""
from ._brain import Answer, Citation, answer

__all__ = ["answer", "Answer", "Citation"]
''',
        "brain": r'''
"""
title: Wiki navigator brain
layer: backend
public_api: no
summary: Plan: deterministic retrieval (query_corpus) -> synthesize a cited answer; on a Runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from models import get_model
from runtimes import END, MODEL_CALL, READ_ONLY, Edge, Plan, Step, get_runtime

__all__ = ["answer", "Answer", "Citation"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_VISIBLE = ("public", "internal")   # confidential/restricted are not surfaced


@dataclass(frozen=True)
class Citation:
    """One traceable source behind an answer."""
    node_id: str
    path: str
    summary_source: str    # "authored" | "generated" — caller can weight authored higher
    owner: str             # resolved owner ("" if unowned)
    owner_source: str      # "marker" | "frontmatter" | "inherited" | "none"


@dataclass(frozen=True)
class Answer:
    """An answer plus full provenance."""
    text: str              # the answer; in dry-run, the prompt that WOULD be sent
    citations: tuple       # tuple[Citation, ...] — every source is traceable
    dry_run: bool


def _run(args):
    """Invoke a repo script via its CLI with the SAME interpreter running us."""
    proc = subprocess.run([sys.executable] + args, cwd=_REPO,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _system_prompt():
    with open(os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8") as fh:
        return fh.read()


def _answer_prompt(question, nodes):
    ctx = "\n".join(
        "- [%s] %s (%s): %s" % (n.get("summary_source") or "gap", n.get("node_id"),
                                n.get("path"), n.get("summary") or n.get("text_excerpt", ""))
        for n in nodes)
    return (_system_prompt()
            + "\n\n# Question\n%s\n\n# Retrieved context (cite by node_id)\n%s\n"
            % (question, ctx or "(nothing retrieved)"))


# --- plan steps ----------------------------------------------------------------
# Retrieval is deterministic and read-only, so it ALWAYS runs (even in dry-run)
# and `citations` is populated regardless. Only the synthesis is a model call,
# so the runtime gates it on execute=True. A failed retrieval fails closed
# (raises) rather than handing the model an empty, hallucination-prone context.

def _retrieve(state):
    """Read-only: query_corpus, fail closed on error, filter by visibility, cite."""
    rc, out, err = _run(["scripts/query_corpus.py", state["question"],
                         "--corpus", state["corpus"],
                         "--max-nodes", str(state["max_nodes"])])
    if rc != 0:
        raise RuntimeError("query_corpus failed (rc=%d): %s" % (rc, err.strip()))
    try:
        hits = json.loads(out) if out.strip() else []
    except ValueError:
        hits = []
    visible = [h for h in hits if (h.get("visibility") or "internal") in _VISIBLE]
    citations = tuple(
        Citation(node_id=h.get("node_id", ""), path=h.get("path", ""),
                 summary_source=h.get("summary_source") or "",
                 owner=h.get("owner") or "",
                 owner_source=h.get("owner_source") or "none")
        for h in visible)
    return {"citations": citations, "prompt": _answer_prompt(state["question"], visible)}


def _synthesize(state):
    """Model-call: synthesize the answer over the retrieved, visible nodes."""
    return {"answer_text": get_model(state.get("model")).run(state["prompt"]).strip()}


_PLAN = Plan(
    name="wiki_answer",
    entry="retrieve",
    steps=(
        Step("retrieve", READ_ONLY, _retrieve),
        Step("synthesize", MODEL_CALL, _synthesize),
    ),
    edges=(
        Edge("retrieve", "synthesize"),
        Edge("synthesize", END),
    ),
)


def answer(question, *, execute=False, model=None, corpus=None, max_nodes=8, runtime=None):
    """Deterministically retrieve candidate nodes (tree+links, via query_corpus),
    then synthesize an answer over them. The pipeline is a neutral ``Plan`` run
    on a ``Runtime`` (default the stdlib ``inprocess`` engine; ``runtime``
    selects another). Retrieval always runs, so ``citations`` is populated even
    in dry-run; only the model call is gated by ``execute``. Honors node
    ``visibility``. Model via ``models.get_model(model)`` -- never a provider name.
    """
    init = {"question": question, "model": model,
            "corpus": corpus or _CORPUS, "max_nodes": max_nodes}
    st = get_runtime(runtime).run(_PLAN, init, execute=execute).state
    citations = st.get("citations", ())
    if execute:
        return Answer(text=st["answer_text"], citations=citations, dry_run=False)
    return Answer(text=st.get("prompt", ""), citations=citations, dry_run=True)
''',
        "prompt": r'''
# Role
You are the **wiki navigator**. You answer a question from the company corpus by
traversing its tree and entity/keyword links, and you cite every source.

# Inputs
- A natural-language question.
- A retrieved neighbourhood of corpus nodes (tree + links) for that question.

# Tools
Your permitted tools are listed in `tools.md`. Retrieval is done by
`query_corpus` (read-only, deterministic); invoke it per its spec in
`agents/tools/`. Never invoke a tool that is not in `tools.md`.

# Procedure
1. Retrieve candidate nodes for the question (deterministic — always run).
2. Answer ONLY from the retrieved nodes. If they do not contain the answer, say so.
3. Cite each claim by `node_id`. Surface provenance: prefer `authored` summaries
   over `generated` ones, and note when a cited node is unowned (`owner_source: none`).
4. Never reveal nodes whose `visibility` is `confidential` or `restricted`.

# Output contract
Return an `Answer`: `text` (the answer, or the prompt in dry-run) and
`citations` (a `Citation` per source: node_id, path, summary_source, owner,
owner_source).

# Safety
- Default to **dry-run** (`execute=False`): retrieval runs and citations are
  populated, but no model is called — `text` holds the prompt that WOULD be sent.
- The model comes from `models/`; never name a provider.
- Authored summaries are more trustworthy than generated ones; weight accordingly.
''',
        "tools": r'''
---
title: wiki_navigator — toolset
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: [agent, toolset, manifest]
summary: The shared tools agents/wiki_navigator is permitted to invoke.
id: agents-wiki-navigator-tools
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# wiki_navigator — toolset

This agent may invoke ONLY the tools below. Each row points at a shared spec in
`agents/tools/`. Adding a tool = add a row here AND add this agent to that
spec's `## Used by` (the binding is bidirectional).

| Tool spec | Effect | Used for |
|-----------|--------|----------|
| `../tools/query_corpus.tool.md` | read-only | retrieve candidate nodes for a question |
''',
    },

]



# --------------------------------------------------------------------------- #
# Automation exemplars: triggers (thin adapters) vs doers (scripts/agents).
# --------------------------------------------------------------------------- #
def automation_examples():
    # --- LLM doer: the triage agent brain (agents/triage) ---
    readme("agents/triage", title="Triage agent", kind="agent", layer="backend",
           public_api="agents/triage/__init__.py",
           tags=["agent", "example", "llm"],
           summary="Example LLM 'brain' that triages an event payload into a short summary.",
           body="""
           An example agent **brain**: it triages an event payload (a failure, a
           diff, a log) into a short summary. A thin doer in `scripts/hooks/` or
           `scripts/jobs/` calls `triage(...)` — the only public symbol.

           It holds reasoning/prompt only: it asks `models/` for a backend by
           name and never hardcodes a provider. Per the repo rules it **defaults
           to a dry run** — `triage(payload)` returns the prompt it *would* send;
           pass `execute=True` to actually run a model.
           """)
    claude("agents/triage", title="agents/triage", layer="backend", rules=[
        "This package is reasoning/prompt only. Get the model from `models/` "
        "(`get_model`); never name a provider here.",
        "`triage()` is the only public symbol — keep prompt/policy in `_brain.py` "
        "private behind `__init__.py`.",
        "Default to dry-run (`execute=False`); calling a model is the authorized "
        "path, not the default.",
    ])
    w("agents/triage/__init__.py", textwrap.dedent('''
        """
        title: Triage agent
        layer: backend
        public_api: yes
        summary: An LLM 'brain' that triages an event payload into a short summary.
        """
        from ._brain import triage

        __all__ = ["triage"]
        ''').strip() + "\n")
    w("agents/triage/_brain.py", textwrap.dedent('''
        """
        title: Triage brain
        layer: backend
        public_api: no
        summary: Builds a triage prompt and (only when authorized) runs it on a model.
        """
        from __future__ import annotations

        from models import get_model

        __all__ = ["triage"]

        _PROMPT = """\\
        You are a triage assistant. Given the event payload below, produce a 3-line
        summary: (1) what happened, (2) likely cause, (3) suggested next action.

        --- payload ---
        {payload}
        """


        def triage(payload: str, *, execute: bool = False, model: str | None = None) -> str:
            """Triage an event payload into a short summary.

            The agent holds only reasoning/policy: it builds the prompt and asks
            ``models/`` for a backend by name — it never hardcodes a provider. Per
            the repo rules a model-calling action defaults to a dry run: with
            ``execute=False`` (the default) we return the rendered prompt and never
            call a model. Pass ``execute=True`` to actually run.
            """
            prompt = _PROMPT.format(payload=payload)
            if not execute:
                return "[dry-run] would run on a model:\\n" + prompt
            return get_model(model).run(prompt)
        ''').strip() + "\n")

    # --- event-hook doers (scripts/hooks) ---
    readme("scripts/hooks", title="Hooks", kind="script", layer="n/a",
           tags=["hooks", "automation", "triggers"],
           summary="Event-triggered doers — the scripts a hook fires. The trigger lives elsewhere.",
           body="""
           Event-triggered **doers**: the scripts that run *when something
           happens*. The script here is the doer; the **trigger** is a thin,
           vendor-specific adapter (`.pre-commit-config.yaml`, `.github/`,
           `.claude/settings.json`, …) that only says "on event → call this
           script" and holds no logic. Deterministic hooks are self-contained
           here; LLM-backed hooks call an agent in `agents/` (which gets its
           model from `models/`). `on_stop_triage.py` is the LLM example.
           """)
    claude("scripts/hooks", title="scripts/hooks", layer="n/a", rules=[
        "A hook script is a **doer**, never a trigger. The trigger (which event "
        "fires it) is a thin, vendor-specific adapter in that ecosystem's config "
        "— keep it out of here and vendor-agnostic across the set.",
        "Hooks fire unattended, possibly on every edit/commit: be fast, "
        "idempotent, safe to run twice; never assume an interactive terminal.",
        "LLM-backed hooks stay thin — call an agent in `agents/` (model from "
        "`models/`). No reasoning or provider names in the hook itself.",
    ])
    w("scripts/hooks/on_stop_triage.py", textwrap.dedent('''
        #!/usr/bin/env python3
        """
        title: on-stop triage hook
        kind: script
        layer: n/a
        summary: Thin event-hook entrypoint — hands a payload to the triage agent.
        """
        from __future__ import annotations

        import argparse
        import os
        import sys

        # A *doer* invoked by some trigger (git hook, CI step, agent-tool hook).
        # The trigger is a thin adapter that only says "run this on event X".
        ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable

        from agents.triage import triage  # noqa: E402  (after sys.path setup)


        def main(argv: list[str] | None = None) -> int:
            ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
            ap.add_argument("payload", nargs="?", default="-",
                            help="event payload, or '-' to read stdin")
            ap.add_argument("--execute", action="store_true",
                            help="actually run the model (default: dry-run preview)")
            ap.add_argument("--model", default=None, help="model name from models/ registry")
            args = ap.parse_args(argv)
            payload = sys.stdin.read() if args.payload == "-" else args.payload
            print(triage(payload, execute=args.execute, model=args.model))
            return 0


        if __name__ == "__main__":
            sys.exit(main())
        ''').strip() + "\n")

    # --- scheduled doers (scripts/jobs) ---
    readme("scripts/jobs", title="Jobs", kind="script", layer="n/a",
           tags=["jobs", "scheduled", "automation", "triggers"],
           summary="Time-triggered doers — the scripts a scheduler fires. The schedule lives in ops/.",
           body="""
           Time-triggered **doers**: the scripts that run *on a schedule*. The
           script is the doer; the **schedule** is a thin, vendor-specific
           adapter in `ops/scheduled/` (cron/systemd/CI/cloud) that records only
           *when* to fire it. Deterministic jobs are self-contained here
           (`rebuild_index.py`); LLM-backed jobs call an agent in `agents/`.
           """)
    claude("scripts/jobs", title="scripts/jobs", layer="n/a", rules=[
        "A job script is a **doer**, never a schedule. The cadence is a thin, "
        "vendor-specific adapter in `ops/scheduled/` — keep the set vendor-agnostic.",
        "Jobs run unattended: idempotent and safe to re-run; a missed or doubled "
        "run must not corrupt state. Exit non-zero on failure so the scheduler alerts.",
        "LLM-backed jobs stay thin — call an agent in `agents/` (model from "
        "`models/`). No reasoning or provider names in the job itself.",
    ])
    w("scripts/jobs/rebuild_index.py", textwrap.dedent('''
        #!/usr/bin/env python3
        """
        title: Rebuild index job
        kind: script
        layer: n/a
        summary: Deterministic scheduled job — regenerates a doc index. No LLM.
        """
        from __future__ import annotations

        import argparse
        import os
        import sys

        ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


        def _title_of(md_path: str) -> str:
            """Pull the frontmatter `title:` from a markdown file (best-effort)."""
            with open(md_path, encoding="utf-8") as fh:
                if not fh.readline().startswith("---"):
                    return os.path.relpath(md_path, ROOT)
                for line in fh:
                    if line.strip() == "---":
                        break
                    if line.startswith("title:"):
                        return line.split(":", 1)[1].strip()
            return os.path.relpath(md_path, ROOT)


        def build_index(root: str) -> str:
            """Markdown index of every README.md under `root`. Pure + idempotent."""
            rows = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames
                               if not d.startswith(".") and d != "__pycache__"]
                if "README.md" in filenames:
                    p = os.path.join(dirpath, "README.md")
                    rows.append("- [%s](%s) — %s" % (
                        os.path.relpath(dirpath, root) or ".",
                        os.path.relpath(p, root), _title_of(p)))
            rows.sort()
            return "# Doc index\\n\\n" + "\\n".join(rows) + "\\n"


        def main(argv: list[str] | None = None) -> int:
            ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
            ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
            ap.add_argument("--out", default="-", help="output file, or '-' for stdout")
            args = ap.parse_args(argv)
            index = build_index(args.root)
            if args.out == "-":
                sys.stdout.write(index)
            else:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(index)
                print("wrote %s" % args.out)
            return 0


        if __name__ == "__main__":
            sys.exit(main())
        ''').strip() + "\n")

    # --- schedule adapters (ops/scheduled): the WHEN, not the WHAT ---
    readme("ops/scheduled", title="Scheduled triggers", kind="ops", layer="n/a",
           tags=["scheduled", "cron", "triggers", "automation"],
           summary="Thin schedule adapters — when to fire a job. The job itself lives in scripts/jobs/.",
           body="""
           The **when**, not the **what**. Each file here is a thin,
           vendor-specific adapter that records a cadence ("trigger in 2 days",
           "02:00 daily") and points at a doer in `scripts/jobs/`. No application
           logic lives here. Pick whichever scheduler your environment uses
           (cron / systemd timers / CI cron / a cloud routine) — the doer never
           changes; a second scheduler is a new thin file, not a forked job.
           """)
    claude("ops/scheduled", title="ops/scheduled", layer="n/a", rules=[
        "Thin **schedule adapters** (the cadence) only — the doer lives in "
        "`scripts/jobs/`. No app logic here.",
        "Keep the set vendor-agnostic: a new scheduler is a new thin file "
        "pointing at the same job, never a fork of the job.",
        "Examples only in the repo (`*.example`); real schedules carry "
        "environment-specific paths/users and are deployed, not committed.",
    ])
    w("ops/scheduled/crontab.example", textwrap.dedent("""
        # Example cron schedule — a thin trigger that only says WHEN.
        # Install with `crontab ops/scheduled/crontab.example` (edit paths/user first).
        # The doer is scripts/jobs/rebuild_index.py — this file holds no logic.
        #
        # ┌ minute ┌ hour ┌ day-of-month ┌ month ┌ day-of-week
        # │        │      │              │       │

        # Rebuild the doc index every day at 02:00.
        0 2 * * * cd /path/to/repo && python3 scripts/jobs/rebuild_index.py --out wiki/INDEX.md

        # systemd-timer equivalent (same doer): [Timer] OnCalendar=*-*-* 02:00:00
        # CI equivalent: a `on: schedule: - cron: '0 2 * * *'` workflow calling the same script.
        """).lstrip() + "")


# --------------------------------------------------------------------------- #
# Third-party tool adapters: thin wrapper in scripts/ + config in config/<tool>/.
# cdmon (code-doc drift monitor) is the worked example (CONVENTIONS §9).
# --------------------------------------------------------------------------- #
def tooling_adapters():
    w("scripts/cdmon_sync.py", textwrap.dedent('''
        #!/usr/bin/env python3
        """
        title: cdmon adapter
        kind: script
        layer: n/a
        summary: Thin wrapper that invokes cdmon — no tool logic lives here.
        """
        from __future__ import annotations

        import argparse
        import os
        import shutil
        import subprocess
        import sys

        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        DEFAULT_CONFIG = os.path.join("config", "cdmon", "cdmon.yaml")


        def main(argv: list[str] | None = None) -> int:
            ap = argparse.ArgumentParser(description="Run cdmon over the repo (thin adapter).")
            ap.add_argument("mode", nargs="?", default="lint",
                            choices=["lint", "heal", "build"],
                            help="cdmon subcommand to run")
            ap.add_argument("--check", action="store_true",
                            help="alias for `lint` (used by pre-commit)")
            ap.add_argument("--config", default=DEFAULT_CONFIG)
            args = ap.parse_args(argv)

            if shutil.which("cdmon") is None:
                # No-op so the hook/CI stays green where cdmon isn't installed.
                print("cdmon not installed; skipping (install it to enable drift checks).")
                return 0
            if not os.path.exists(os.path.join(ROOT, args.config)):
                print(f"no cdmon config at {args.config}; skipping.")
                return 0

            mode = "lint" if args.check else args.mode
            return subprocess.run(["cdmon", mode, "--config", args.config], cwd=ROOT).returncode


        if __name__ == "__main__":
            sys.exit(main())
        ''').strip() + "\n")
    w("config/cdmon/cdmon.example.yaml", textwrap.dedent("""
        # Example cdmon config. Copy to cdmon.yaml and register the docs cdmon
        # should manage. cdmon owns the `cdm:` frontmatter block and CDM:BEGIN/END
        # regions; this template owns the top-level keys (CONVENTIONS §9).
        # Keep each doc's `id` here equal to its frontmatter `id`.
        version: 1
        output:
          dir: .cdmon            # generated; gitignored
          html: false            # pick cdmon twins OR wiki/, not both
        documents:
          - id: readme
            path: README.md
            audience: eng-guide
          # - id: backend-readme
          #   path: src/backend/README.md
          #   audience: eng-guide
        """).strip() + "\n")


# --------------------------------------------------------------------------- #
# The wiki "one brain": deterministic corpus scripts + shared agent tools +
# the index_enforcer and wiki_navigator example agents (CONVENTIONS §10-§13).
# --------------------------------------------------------------------------- #
def wiki_agents():
    # --- deterministic corpus toolkit (scripts/) ---
    w("scripts/jobs/build_corpus.py", textwrap.dedent(_BUILD_CORPUS_SRC).strip() + "\n")
    w("scripts/jobs/link_corpus.py", textwrap.dedent(_LINK_CORPUS_SRC).strip() + "\n")
    w("scripts/query_corpus.py", textwrap.dedent(_QUERY_CORPUS_SRC).strip() + "\n")
    w("scripts/accountability_report.py",
      textwrap.dedent(_ACCOUNTABILITY_SRC).strip() + "\n")

    # --- shared tool-use specs (agents/tools/) ---
    readme("agents/tools", title="Agent tools", kind="doc", layer="cross-cutting",
           tags=["tools", "agents", "adapters"],
           summary="Shared, thin TOOL.md tool-use specs — how an agent invokes a scripts/ doer.",
           body="""
           Each `*.tool.md` is a **thin adapter**: it tells any LLM agent *how to
           invoke* a doer in `scripts/` — the tool's logic stays in the script,
           never here (same rule as transports in §7 and third-party tools in §9).
           Tools live here because they are **shared across agents**; an agent
           declares which it may use in its own `tools.md` manifest.

           Each spec carries `kind: tool` frontmatter with `public_api` (the
           wrapped script, validated to exist), `tool_command` (the exact argv),
           and `tool_effect` (`read-only` | `writes` | `model-call`). Adding a
           tool = add a `*.tool.md` here AND list it in the using agent's
           `tools.md` (`## Used by` and the manifest row are bidirectional).
           """)
    claude("agents/tools", title="agents/tools", layer="cross-cutting", rules=[
        "A `*.tool.md` is a **thin adapter**: it documents how to invoke a "
        "`scripts/` doer. Never put tool logic here — it belongs in the script.",
        "Frontmatter is governed: `kind: tool`, a real `owner` (not `TBD`), a "
        "`public_api` that resolves to the wrapped script, and a valid `tool_effect`.",
        "Keep `tool_command` consistent with `public_api`, and `## Used by` in "
        "sync with each agent's `tools.md` (the binding is bidirectional).",
        "Specs are vendor-agnostic: describe the tool so any agent/LLM can use "
        "it; never name a provider.",
    ])
    for name, body in _TOOL_SPECS:
        w("agents/tools/%s.tool.md" % name, body.strip() + "\n")

    # --- the two example agents ---
    for spec in _WIKI_AGENT_DIRS:
        d = spec["dir"]
        readme(d, title=spec["title"], kind="agent", layer="backend",
               public_api="%s/__init__.py" % d, tags=spec["tags"],
               summary=spec["summary"], body=spec["readme_body"])
        claude(d, title=d, layer="backend", rules=spec["rules"])
        w("%s/__init__.py" % d, textwrap.dedent(spec["init"]).strip() + "\n")
        w("%s/_brain.py" % d, textwrap.dedent(spec["brain"]).strip() + "\n")
        w("%s/prompt.md" % d, textwrap.dedent(spec["prompt"]).strip() + "\n")
        w("%s/tools.md" % d, spec["tools"].strip() + "\n")






# === BEGIN agent_surface (generated by /tmp/gen_agent_surface.py) ===
# Content constants mirror the live agent-surface files byte-for-byte;
# they are machine-generated — edit the live files then re-run the generator.
_AS_MODELS_SRC = r'''"""
title: Agent surface models
layer: backend
public_api: no
summary: Vendor-neutral value objects an agent surface speaks: card, reply, capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["AgentKind", "Capability", "AgentCard", "AgentReply"]


class AgentKind(str, Enum):
    """The single role dimension that classifies an agent surface."""

    WIKI = "wiki"
    WORKER = "worker"
    TEAMMATE = "teammate"
    AMBIENT = "ambient"


@dataclass(frozen=True)
class Capability:
    """One named action a surface advertises (rendered on its card)."""

    command: str          # e.g. "/ask"
    title: str            # human label
    arg_hint: str = ""    # e.g. "<question>"
    description: str = ""


@dataclass(frozen=True)
class AgentCard:
    """Vendor-neutral self-description of a service reachable as an agent.

    This is the *vocabulary* every wire dialect (AAD, A2A, an MCP-native
    descriptor, ...) renders from; it carries no dialect-specific fields (no
    well-known path, no version envelope, no transport binding) — those belong
    to an adapter, never here.
    """

    slug: str
    name: str
    kind: AgentKind = AgentKind.WORKER
    tagline: str = ""
    description: str = ""
    owner: str = ""
    tags: tuple[str, ...] = ()
    capabilities: tuple[Capability, ...] = ()
    example_prompts: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentReply:
    """A single answer from a surface, plus optional presentation/meta/error.

    Field names are neutral; a wire adapter maps them onto its own payload
    (e.g. AAD's `io` map) so the surface never hard-codes a dialect's keys.
    """

    answer: str
    meta: str = ""
    html: str = ""
    error: str = ""
'''

_AS_CONTRACTS_SRC = r'''"""
title: Agent surface contract
layer: backend
public_api: yes
summary: The vendor-neutral AgentSurface interface a wire adapter (AAD, A2A, ...) renders.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ._models import AgentCard, AgentReply

__all__ = ["AgentSurface"]


@runtime_checkable
class AgentSurface(Protocol):
    """A service that can be reached as an agent.

    Implement these three methods and any wire dialect can expose you:
    `card()` self-describes, `ask()` answers a single question, `health()`
    reports liveness. Depend on THIS, never on a concrete wire format — the
    dialect (AAD today; A2A / a plugin manifest tomorrow) is a thin adapter
    that serializes a surface, registered alongside, never baked in here.
    """

    def card(self) -> AgentCard:
        """Return this service's vendor-neutral self-description."""
        ...

    def ask(self, question: str) -> AgentReply:
        """Answer one question; return a neutral reply (answer + optional meta/html/error)."""
        ...

    def health(self) -> dict:
        """Return a liveness payload, e.g. ``{"status": "ok"}``."""
        ...
'''

_AS_INIT_SRC = r'''"""
title: Agent surface (vendor-neutral)
layer: backend
public_api: yes
summary: AgentSurface contract + neutral card/reply a service implements to be reachable as an agent.
"""
from ._models import AgentCard, AgentKind, AgentReply, Capability
from .contracts import AgentSurface

__all__ = ["AgentSurface", "AgentCard", "AgentReply", "Capability", "AgentKind"]
'''

_AAD_DESCRIPTOR_SRC = r'''"""
title: AAD descriptor (Aion Agent Discovery wire format)
layer: backend
public_api: yes
summary: AAD-specific wire model + renderer that serializes a neutral AgentCard to an AAD descriptor.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # the neutral contract this dialect serializes (no runtime dep)
    from backend.agent_surface import AgentCard

__all__ = ["AadDescriptor", "card_to_aad", "AAD_VERSION"]

# Wire-format version, MAJOR.MINOR. MINOR is additive-only (a reader that knows
# an older minor ignores unknown fields); MAJOR is breaking. Never mutate a
# shipped field — only add (minor) or open a new major. See docs/adr.
AAD_VERSION = "1.0"


class _Aad(BaseModel):
    """Base for every AAD model.

    ``extra="ignore"`` is the forward-compatibility rule: a reader that knows
    only an older AAD minor silently drops fields a newer minor added, instead
    of erroring on them.
    """

    model_config = ConfigDict(extra="ignore")


class AadProtocol(str, Enum):
    """Wire protocols an external agent may declare (no ``function`` — that is
    an in-process transport, not something discovered over a URL)."""

    OPENAPI = "openapi"
    MCP = "mcp"


class AadAuthKind(str, Enum):
    """How the consumer must authenticate. ``none`` is DEV-ONLY."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"


class AadIo(_Aad):
    """Which response field carries which part of the answer — the semantics
    OpenAPI omits."""

    question: str = "question"
    answer: str = "answer"
    meta: str | None = None
    html: str | None = None
    error: str | None = None


class AadOperation(_Aad):
    """Binds a logical role (ask/stream) to an OpenAPI operation + its io map."""

    operationId: str | None = None  # noqa: N815 — mirrors the OpenAPI field name
    path: str | None = None
    method: str | None = None
    sse: bool = False
    io: AadIo = Field(default_factory=AadIo)


class AadOpenApi(_Aad):
    """OpenAPI transport binding: where the spec is and which ops to resolve."""

    spec_url: str = "/openapi.json"
    operations: dict[str, AadOperation] = Field(default_factory=dict)


class AadMcp(_Aad):
    """MCP transport binding (alternative to OpenAPI)."""

    endpoint: str
    tool: str = "ask"


class AadAuth(_Aad):
    """Declares *that* auth is needed; never the secret (that stays consumer-side)."""

    kind: AadAuthKind = AadAuthKind.NONE
    header: str | None = None


class AadTransport(_Aad):
    """How to call the agent: the protocol + its binding + auth declaration."""

    protocol: AadProtocol
    openapi: AadOpenApi | None = None
    mcp: AadMcp | None = None
    auth: AadAuth = Field(default_factory=AadAuth)


class AadHealth(_Aad):
    """Liveness endpoint the consumer may poll."""

    path: str | None = None
    method: str = "GET"


class AadCapability(_Aad):
    """A slash command the agent exposes (rendered on its card)."""

    command: str
    title: str
    arg_hint: str | None = None
    maps_to: str | None = None
    passthrough: str | None = None


class AadIcon(_Aad):
    """Presentation-only monogram/gradient for the agent card."""

    kind: str = "monogram"
    text: str = "AI"
    gradient: list[str] = Field(default_factory=lambda: ["#a8c400", "#40c878"])


class AadAgent(_Aad):
    """The card half of the descriptor — display metadata for the agents UI."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str
    kind: str
    tagline: str = ""
    description: str = ""
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    icon: AadIcon = Field(default_factory=AadIcon)
    capabilities: list[AadCapability] = Field(default_factory=list)
    example_prompts: list[str] = Field(default_factory=list)


class AadDescriptor(_Aad):
    """The document an agent serves at ``/.well-known/aion-agent.json`` (AAD v1).

    This is the AAD *dialect* of the neutral agent surface — the version
    envelope, transport binding, and well-known path live here, never in the
    neutral ``AgentCard``. ``AadDescriptor.model_json_schema()`` is the single
    source of truth the committed JSON Schema is generated from.
    """

    aad_version: str
    agent: AadAgent
    transport: AadTransport
    health: AadHealth | None = None


def card_to_aad(card: AgentCard, *, ask_operation_id: str = "ask",
                spec_url: str = "/openapi.json", health_path: str = "/health",
                auth_kind: str = "none") -> dict:
    """Render a neutral ``AgentCard`` into an AAD v1 descriptor dict.

    Every AAD-specific shape — the ``aad_version`` envelope, the OpenAPI
    transport binding, the ``io`` field map, the health pointer — is produced
    HERE. The neutral card knows none of it, which is what lets a second
    dialect (A2A, a plugin manifest) be a sibling renderer, not a rewrite.
    ``auth_kind="none"`` is a DEV default; production must declare real auth.
    """
    capabilities = []
    for c in card.capabilities:
        cap = {"command": c.command, "title": c.title,
               "maps_to": "ask", "passthrough": "rawArgs"}
        if c.arg_hint:
            cap["arg_hint"] = c.arg_hint
        capabilities.append(cap)
    kind = card.kind.value if hasattr(card.kind, "value") else str(card.kind)
    payload = {
        "aad_version": AAD_VERSION,
        "agent": {
            "slug": card.slug,
            "name": card.name,
            "kind": kind,
            "tagline": card.tagline,
            "description": card.description,
            "owner": card.owner,
            "tags": list(card.tags),
            "capabilities": capabilities,
            "example_prompts": list(card.example_prompts),
        },
        "transport": {
            "protocol": "openapi",
            "openapi": {
                "spec_url": spec_url,
                "operations": {
                    "ask": {
                        "operationId": ask_operation_id,
                        "io": {"question": "question", "answer": "answer",
                               "meta": "meta", "html": "html", "error": "error"},
                    },
                },
            },
            "auth": {"kind": auth_kind},
        },
        "health": {"path": health_path, "method": "GET"},
    }
    # Fail EARLY (at router build / import) on a malformed descriptor — e.g. an
    # author slug that breaks AadAgent's pattern — instead of serving a
    # non-conformant document. Validate against the model that is the schema's
    # source of truth, but return the literal dict so the served wire shape is
    # exactly what we control here (no default-field expansion).
    AadDescriptor.model_validate(payload)
    return payload
'''

_AAD_ROUTER_SRC = r'''"""
title: AAD FastAPI router
layer: backend
public_api: yes
summary: Mount any AgentSurface as an AAD-discoverable agent (descriptor + ask + health).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .descriptor import card_to_aad

if TYPE_CHECKING:
    from backend.agent_surface import AgentSurface

__all__ = ["build_aad_router"]


class _AskBody(BaseModel):
    """Request body for the AAD ask endpoint (the `io.question` field)."""

    question: str


def build_aad_router(surface: AgentSurface, *, ask_path: str = "/ask",
                     health_path: str = "/health",
                     auth_kind: str = "none") -> APIRouter:
    """Return a FastAPI router that exposes ``surface`` over the AAD wire contract.

    Wires the four AAD endpoints by adapting the neutral ``AgentSurface``:
    the well-known descriptor (+ the dot-less ``/aion-agent.json`` fallback for
    servers that can't serve a dot-directory), ``POST`` ask, and ``GET`` health.
    ``/openapi.json`` is emitted by FastAPI itself, so the descriptor's ``ask``
    operationId resolves against the app's own generated spec — no hand-written
    OpenAPI. Mount with ``app.include_router(build_aad_router(MySurface()))``.

    The vendor (AAD) shape is confined to this adapter; the surface stays
    neutral, so a second dialect is a sibling router, not a change here.
    """
    router = APIRouter()
    descriptor = card_to_aad(surface.card(), ask_operation_id="ask",
                             health_path=health_path, auth_kind=auth_kind)

    @router.get("/.well-known/aion-agent.json")
    def aad_descriptor() -> JSONResponse:
        return JSONResponse(descriptor)

    # RFC 8615 dot-directory fallback: some servers (e.g. Astro file-routing)
    # cannot serve `/.well-known/...`; the consumer tries this path next.
    @router.get("/aion-agent.json")
    def aad_descriptor_fallback() -> JSONResponse:
        return JSONResponse(descriptor)

    @router.post(ask_path, operation_id="ask")
    def ask(body: _AskBody) -> dict:
        reply = surface.ask(body.question)
        return {"answer": reply.answer, "meta": reply.meta,
                "html": reply.html, "error": reply.error}

    @router.get(health_path)
    def health() -> dict:
        return surface.health()

    return router
'''

_AAD_INIT_SRC = r'''"""
title: AAD adapter
layer: backend
public_api: yes
summary: Expose a neutral AgentSurface over the AAD wire format (descriptor + ask + health).
"""
from .descriptor import AAD_VERSION, AadDescriptor, card_to_aad
from .router import build_aad_router

__all__ = ["build_aad_router", "card_to_aad", "AadDescriptor", "AAD_VERSION"]
'''

_AAD_README = r'''---
title: API — AAD agent-surface adapter
kind: api
layer: backend
status: template
owner: TBD
public_api: api/rest_fastapi/aad/__init__.py
tags: [api, agent, surface, aad, adapter]
summary: Thin FastAPI adapter exposing a neutral AgentSurface over the AAD wire format.
id: api-rest-fastapi-aad-readme
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# API — AAD agent-surface adapter

Thin FastAPI adapter exposing a neutral AgentSurface over the AAD wire format.

A FastAPI router that makes any service implementing the vendor-neutral
`AgentSurface` (`src/backend/agent_surface/`) discoverable as an agent over
**AAD** (the Aion Agent Discovery wire format). AAD is ONE dialect of the
agent-surface concept; it lives here, in the transport layer, exactly as a
model provider lives behind `models/`. To add another dialect (A2A, an
MCP-native descriptor, a plugin manifest), drop a sibling router next to this
one — the neutral contract in `src/` does not change.

## Mount it

```python
from backend.agent_surface import AgentSurface   # the neutral contract
from aad import build_aad_router                  # this adapter

app.include_router(build_aad_router(my_surface))
```

## The 4-endpoint contract it serves

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/.well-known/aion-agent.json` | GET | the **AAD descriptor** — card + how to call you (fallback `/aion-agent.json` for servers that can't serve a dot-directory) |
| `/openapi.json` | GET | FastAPI emits this for free; the descriptor's `ask` binds to an `operationId` in it |
| `/ask` | POST | `{question}` → `{answer, meta, html, error}` (field names declared in the descriptor's `io` map) |
| `/health` | GET | liveness |

## Files

- `descriptor.py` — the AAD wire model (`AadDescriptor`) + `card_to_aad`, the
  renderer that maps a neutral `AgentCard` to AAD JSON. The AAD-specific shape
  (version envelope, transport binding, `io` map) is confined here.
- `router.py` — `build_aad_router(surface)`; wires the four endpoints.

## Versioning & auth

`aad_version` is `MAJOR.MINOR`: a new minor is additive-only (older readers
ignore unknown fields); a major is breaking; a shipped field is never mutated.
`auth.kind: none` is a **dev** default — a production agent declares real auth,
and the secret stays on the consumer side (the descriptor only says *that* a
header is needed). See `docs/guides/agent-surface.md` and the ADR.

> Out of scope here: *discovering* others' agents (fetch + SSRF allowlist +
> version normalization). A template service only **serves** its own
> descriptor; the consumer side is the chat platform's concern.
'''

_AAD_AGENT = r'''---
title: api/rest_fastapi/aad — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside api/rest_fastapi/aad/.
id: api-rest-fastapi-aad-agent
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# Agent rules — `api/rest_fastapi/aad/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Thin adapter only: map a neutral `AgentSurface` (from `backend.agent_surface`) onto the AAD wire shape. No domain logic or business state here.
- The vendor (AAD) lives ONLY here. The neutral contract in `src/backend/agent_surface/` must never import or name AAD; a second dialect is a sibling adapter, not an edit to the contract.
- `auth.kind: none` is a DEV default; a production descriptor must declare real auth, and the secret stays consumer-side, never in the descriptor.
- The committed schema (`config/agent_surface/aad-v1.0.schema.json`) is generated from `AadDescriptor` — regenerate it (`make agent-surface-schema`) when the model changes; never hand-edit it.
'''

_AAD_SCHEMA_JSON = r'''{
  "$comment": "GENERATED from api/rest_fastapi/aad (descriptor.py); AAD v1.0. Do not hand-edit \u2014 run scripts/agent_surface/generate_aad_schema.py.",
  "$defs": {
    "AadAgent": {
      "description": "The card half of the descriptor \u2014 display metadata for the agents UI.",
      "properties": {
        "capabilities": {
          "items": {
            "$ref": "#/$defs/AadCapability"
          },
          "title": "Capabilities",
          "type": "array"
        },
        "description": {
          "default": "",
          "title": "Description",
          "type": "string"
        },
        "example_prompts": {
          "items": {
            "type": "string"
          },
          "title": "Example Prompts",
          "type": "array"
        },
        "icon": {
          "$ref": "#/$defs/AadIcon"
        },
        "kind": {
          "title": "Kind",
          "type": "string"
        },
        "name": {
          "title": "Name",
          "type": "string"
        },
        "owner": {
          "default": "",
          "title": "Owner",
          "type": "string"
        },
        "slug": {
          "pattern": "^[a-z0-9][a-z0-9-]{0,63}$",
          "title": "Slug",
          "type": "string"
        },
        "tagline": {
          "default": "",
          "title": "Tagline",
          "type": "string"
        },
        "tags": {
          "items": {
            "type": "string"
          },
          "title": "Tags",
          "type": "array"
        }
      },
      "required": [
        "slug",
        "name",
        "kind"
      ],
      "title": "AadAgent",
      "type": "object"
    },
    "AadAuth": {
      "description": "Declares *that* auth is needed; never the secret (that stays consumer-side).",
      "properties": {
        "header": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Header"
        },
        "kind": {
          "$ref": "#/$defs/AadAuthKind",
          "default": "none"
        }
      },
      "title": "AadAuth",
      "type": "object"
    },
    "AadAuthKind": {
      "description": "How the consumer must authenticate. ``none`` is DEV-ONLY.",
      "enum": [
        "none",
        "api_key",
        "bearer"
      ],
      "title": "AadAuthKind",
      "type": "string"
    },
    "AadCapability": {
      "description": "A slash command the agent exposes (rendered on its card).",
      "properties": {
        "arg_hint": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Arg Hint"
        },
        "command": {
          "title": "Command",
          "type": "string"
        },
        "maps_to": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Maps To"
        },
        "passthrough": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Passthrough"
        },
        "title": {
          "title": "Title",
          "type": "string"
        }
      },
      "required": [
        "command",
        "title"
      ],
      "title": "AadCapability",
      "type": "object"
    },
    "AadHealth": {
      "description": "Liveness endpoint the consumer may poll.",
      "properties": {
        "method": {
          "default": "GET",
          "title": "Method",
          "type": "string"
        },
        "path": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Path"
        }
      },
      "title": "AadHealth",
      "type": "object"
    },
    "AadIcon": {
      "description": "Presentation-only monogram/gradient for the agent card.",
      "properties": {
        "gradient": {
          "items": {
            "type": "string"
          },
          "title": "Gradient",
          "type": "array"
        },
        "kind": {
          "default": "monogram",
          "title": "Kind",
          "type": "string"
        },
        "text": {
          "default": "AI",
          "title": "Text",
          "type": "string"
        }
      },
      "title": "AadIcon",
      "type": "object"
    },
    "AadIo": {
      "description": "Which response field carries which part of the answer \u2014 the semantics\nOpenAPI omits.",
      "properties": {
        "answer": {
          "default": "answer",
          "title": "Answer",
          "type": "string"
        },
        "error": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Error"
        },
        "html": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Html"
        },
        "meta": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Meta"
        },
        "question": {
          "default": "question",
          "title": "Question",
          "type": "string"
        }
      },
      "title": "AadIo",
      "type": "object"
    },
    "AadMcp": {
      "description": "MCP transport binding (alternative to OpenAPI).",
      "properties": {
        "endpoint": {
          "title": "Endpoint",
          "type": "string"
        },
        "tool": {
          "default": "ask",
          "title": "Tool",
          "type": "string"
        }
      },
      "required": [
        "endpoint"
      ],
      "title": "AadMcp",
      "type": "object"
    },
    "AadOpenApi": {
      "description": "OpenAPI transport binding: where the spec is and which ops to resolve.",
      "properties": {
        "operations": {
          "additionalProperties": {
            "$ref": "#/$defs/AadOperation"
          },
          "title": "Operations",
          "type": "object"
        },
        "spec_url": {
          "default": "/openapi.json",
          "title": "Spec Url",
          "type": "string"
        }
      },
      "title": "AadOpenApi",
      "type": "object"
    },
    "AadOperation": {
      "description": "Binds a logical role (ask/stream) to an OpenAPI operation + its io map.",
      "properties": {
        "io": {
          "$ref": "#/$defs/AadIo"
        },
        "method": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Method"
        },
        "operationId": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Operationid"
        },
        "path": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Path"
        },
        "sse": {
          "default": false,
          "title": "Sse",
          "type": "boolean"
        }
      },
      "title": "AadOperation",
      "type": "object"
    },
    "AadProtocol": {
      "description": "Wire protocols an external agent may declare (no ``function`` \u2014 that is\nan in-process transport, not something discovered over a URL).",
      "enum": [
        "openapi",
        "mcp"
      ],
      "title": "AadProtocol",
      "type": "string"
    },
    "AadTransport": {
      "description": "How to call the agent: the protocol + its binding + auth declaration.",
      "properties": {
        "auth": {
          "$ref": "#/$defs/AadAuth"
        },
        "mcp": {
          "anyOf": [
            {
              "$ref": "#/$defs/AadMcp"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "openapi": {
          "anyOf": [
            {
              "$ref": "#/$defs/AadOpenApi"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "protocol": {
          "$ref": "#/$defs/AadProtocol"
        }
      },
      "required": [
        "protocol"
      ],
      "title": "AadTransport",
      "type": "object"
    }
  },
  "description": "The document an agent serves at ``/.well-known/aion-agent.json`` (AAD v1).\n\nThis is the AAD *dialect* of the neutral agent surface \u2014 the version\nenvelope, transport binding, and well-known path live here, never in the\nneutral ``AgentCard``. ``AadDescriptor.model_json_schema()`` is the single\nsource of truth the committed JSON Schema is generated from.",
  "properties": {
    "aad_version": {
      "title": "Aad Version",
      "type": "string"
    },
    "agent": {
      "$ref": "#/$defs/AadAgent"
    },
    "health": {
      "anyOf": [
        {
          "$ref": "#/$defs/AadHealth"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "transport": {
      "$ref": "#/$defs/AadTransport"
    }
  },
  "required": [
    "aad_version",
    "agent",
    "transport"
  ],
  "title": "AadDescriptor",
  "type": "object"
}
'''

_AAD_GEN_SRC = r'''"""
title: Generate the AAD JSON Schema
kind: script
layer: backend
summary: Emit config/agent_surface/aad-v1.0.schema.json from the AadDescriptor model (one source of truth).
"""
# NB: no `from __future__ import annotations` here on purpose — the pre-commit
# --check hook may run under an old `python3`, and this file must still parse
# so the graceful skip below can fire. Keep annotations 3.x-safe.
import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_OUT = os.path.join("config", "agent_surface", "aad-v1.0.schema.json")


def _schema() -> dict:
    """Build the JSON Schema from the pydantic AadDescriptor model."""
    sys.path.insert(0, os.path.join(_ROOT, "api", "rest_fastapi"))
    from aad import AAD_VERSION, AadDescriptor  # imported here so --help needs no deps

    schema = AadDescriptor.model_json_schema()
    schema["$comment"] = (
        "GENERATED from api/rest_fastapi/aad (descriptor.py); AAD v%s. "
        "Do not hand-edit — run scripts/agent_surface/generate_aad_schema.py." % AAD_VERSION
    )
    return schema


def main(argv=None) -> int:
    """Write (or --check) the committed AAD JSON Schema.

    Requires pydantic (run under the project interpreter, not a bare 3.6). The
    committed schema is the contract the conformance test validates against —
    keep it generated, never hand-maintained.
    """
    ap = argparse.ArgumentParser(description="Generate the AAD JSON Schema from the model")
    ap.add_argument("--out", default=_OUT, help="output path (default: %s)" % _OUT)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed schema is stale (CI / pre-commit)")
    opts = ap.parse_args(argv)

    try:
        text = json.dumps(_schema(), indent=2, sort_keys=True) + "\n"
    except Exception as exc:  # noqa: BLE001 — best-effort drift guard
        # Old interpreter (can't parse the adapter) or pydantic absent. For
        # --check this is a no-op (like cdmon when not installed); a real
        # `make agent-surface-schema` runs under the project interpreter.
        detail = "%s: %s" % (type(exc).__name__, exc)
        if opts.check:
            sys.stderr.write("AAD schema check skipped (%s)\n" % detail)
            return 0
        sys.stderr.write("AAD schema cannot be generated (%s)\n" % detail)
        return 1
    path = os.path.join(_ROOT, opts.out)
    if opts.check:
        try:
            with open(path, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            current = ""
        if current != text:
            sys.stderr.write(
                "AAD schema is stale; regenerate with "
                "`python scripts/agent_surface/generate_aad_schema.py`\n")
            return 1
        print("AAD schema up to date")
        return 0

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote", opts.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_AAD_DEMO_APP_SRC = r'''"""
title: AAD reference agent
kind: demo
layer: backend
summary: Minimal runnable service that implements AgentSurface and is AAD-discoverable.
"""
from __future__ import annotations

import argparse
import os
import sys

# This demo plays a real consumer: it imports the neutral contract from src/
# and the AAD adapter from api/ via the same path shim the api app uses. A
# real, installed service (`pip install -e .`) drops these two lines.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, os.path.join(_ROOT, "api", "rest_fastapi"))

from fastapi import FastAPI  # noqa: E402

from aad import build_aad_router, card_to_aad  # noqa: E402
from backend.agent_surface import (  # noqa: E402
    AgentCard,
    AgentKind,
    AgentReply,
    AgentSurface,
    Capability,
)

__all__ = ["EchoSurface", "build_app", "app", "DESCRIPTOR"]


class EchoSurface(AgentSurface):
    """The whole job of "becoming an agent": implement card/ask/health.

    Swap the body of `ask` for real logic; everything else — the descriptor,
    the wire endpoints, the OpenAPI doc — is supplied by the AAD adapter.
    """

    def card(self) -> AgentCard:
        """Self-describe: the slug/name/kind/capabilities the agents UI renders."""
        return AgentCard(
            slug="aad-reference-agent",
            name="AAD Reference Agent",
            kind=AgentKind.WIKI,
            tagline="A minimal self-describing agent you can copy.",
            description="Template showing the agent-surface + AAD adapter; echoes the question.",
            owner="you@example.com",
            tags=("template", "reference"),
            capabilities=(Capability(command="/ask", title="Ask a question",
                                     arg_hint="<question>"),),
            example_prompts=("ping", "what can you do?"),
        )

    def ask(self, question: str) -> AgentReply:
        """Answer one question. Replace this body with your real logic."""
        answer = ("You asked: %s\n\n(This is the reference agent — replace "
                  "`ask` with real logic.)" % question)
        return AgentReply(answer=answer, meta="turns: 1 · reference",
                          html="<p>%s</p>" % answer)

    def health(self) -> dict:
        """Liveness."""
        return {"status": "ok"}


def build_app() -> FastAPI:
    """Build the FastAPI app: mount the AAD adapter over the EchoSurface."""
    application = FastAPI(title="AAD Reference Agent", version="1.0.0")
    application.include_router(build_aad_router(EchoSurface()))
    return application


# The descriptor this agent serves (handy for tests/inspection); the adapter
# also serves it live at /.well-known/aion-agent.json.
DESCRIPTOR: dict = card_to_aad(EchoSurface().card())
app = build_app()


def main() -> int:
    """Run the agent with uvicorn; then POST /agents/discover its base URL."""
    ap = argparse.ArgumentParser(description="AAD reference agent")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=51000)
    opts = ap.parse_args()
    import uvicorn

    uvicorn.run(app, host=opts.host, port=opts.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
'''

_AAD_DEMO_INIT_SRC = r'''"""
title: AAD reference agent package
kind: demo
layer: backend
public_api: yes
summary: Re-exports the runnable AAD reference agent (app + descriptor).
"""
from .app import DESCRIPTOR, EchoSurface, app, build_app

__all__ = ["app", "build_app", "EchoSurface", "DESCRIPTOR"]
'''

_AAD_DEMO_README = r'''---
title: AAD Reference Agent (copy-paste template)
kind: demo
layer: backend
status: template
owner: TBD
public_api: demo/aad_reference_agent/__init__.py
tags: [demo, agent, surface, aad, template]
summary: Runnable example — implement AgentSurface, mount the AAD adapter, become discoverable.
id: demo-aad-reference-agent-readme
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# AAD Reference Agent (copy-paste template)

Runnable example — implement AgentSurface, mount the AAD adapter, become discoverable.

The shortest path from "a service" to "a discoverable agent". It implements the
vendor-neutral [`AgentSurface`](../../src/backend/agent_surface/) (three methods:
`card` / `ask` / `health`) and mounts the
[AAD adapter](../../api/rest_fastapi/aad/) — which serves the descriptor, the
`ask`/`health` endpoints, and (via FastAPI) `/openapi.json` for free.

## Run it

```bash
python demo/aad_reference_agent/app.py --host 127.0.0.1 --port 51000
# the descriptor is then served at:
#   GET http://127.0.0.1:51000/.well-known/aion-agent.json
```

A discovery-capable platform onboards it from the base URL alone (e.g. a
`POST /agents/discover {"base_url": "..."}`); no platform-side code per agent.

## Make it yours

1. Edit `EchoSurface.card()` — slug, name, kind, capabilities, example prompts.
2. Replace the body of `EchoSurface.ask()` with real logic (keep returning an
   `AgentReply`).
3. Production auth: pass `auth_kind="api_key"` (etc.) to `build_aad_router`; the
   secret stays on the consumer side, never in the descriptor.
4. Want a different wire dialect later (A2A, a plugin manifest)? Mount a sibling
   adapter over the *same* `EchoSurface` — the surface does not change.

The conformance test (`tests/integration/test_aad_conformance.py`) runs this
agent and asserts its served descriptor validates against the committed schema
and that its `ask` binding resolves against its own `/openapi.json`.
'''

_AAD_DEMO_AGENT = r'''---
title: demo/aad_reference_agent — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside demo/aad_reference_agent/.
id: demo-aad-reference-agent-agent
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# Agent rules — `demo/aad_reference_agent/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- This is a runnable demo, not the adapter: keep it thin. Implement `AgentSurface` and mount `build_aad_router`; do not reimplement the AAD wire shape here.
- Keep it runnable with no deps beyond FastAPI/uvicorn (already in `api/rest_fastapi/requirements.txt`). A broken demo is a bug.
- Keep the served descriptor conformant: the `slug` must match `[a-z0-9][a-z0-9-]{0,63}`, and the `ask` binding must resolve in the app's own `/openapi.json`. The conformance test enforces both — keep it passing.
- `auth.kind: none` here is dev-only; never present this demo as a production-ready default.
'''

_AGENT_SURFACE_GUIDE = r'''---
title: Exposing a service as an agent (the agent surface)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [agent, surface, aad, discovery, guide]
summary: When and how to make a service discoverable as an agent — the neutral surface + a wire adapter (AAD).
id: docs-guides-agent-surface
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# Exposing a service as an agent (the agent surface)

A chat/agent platform that onboards services wants the inverse of hand-wiring
each one: every service **describes itself**, and the platform connects it from
a single base URL. This template encodes that contract the way it encodes every
integration — **neutral concept first, vendor wiring in a thin adapter.**

## The one rule

| Your service… | Becomes an agent via | Why |
|---------------|----------------------|-----|
| **crosses a process boundary** (its own port/URL) | an **agent surface** (self-describe + ask + health), published in a wire dialect | it already has a network contract; publishing a descriptor is cheap and removes per-agent platform code |
| **is compiled in-process** (a brain the host imports) | nothing — stay an in-process function | there is no URL to discover and no wire to version; adding HTTP would be pure cost |

Do **not** add a network boundary just to be uniform. Uniformity is the
*interface* (card + ask + health), not the *transport*.

## The neutral concept vs the dialect

The **agent surface** is vendor-neutral: a service self-describes (a card:
slug/name/kind/capabilities), answers a question (`ask`), and reports liveness
(`health`). That is the whole concept, stated with no vendor in it.

- **Contract** — [`src/backend/agent_surface/`](../../src/backend/agent_surface/):
  the `AgentSurface` protocol + neutral `AgentCard` / `AgentReply`. No wire
  format, no version envelope, no well-known path. This is what your code
  implements.
- **Dialect (adapter)** — [`api/rest_fastapi/aad/`](../../api/rest_fastapi/aad/):
  **AAD** (Aion Agent Discovery) is *one* wire format that serializes a surface
  — descriptor at `/.well-known/aion-agent.json`, `ask`/`health`, OpenAPI for
  free. It lives in the transport layer, exactly as a model provider lives
  behind `models/`. A second dialect (A2A, an MCP-native descriptor, an
  OpenAI-style plugin manifest) is a **sibling adapter over the same surface**,
  never a change to the contract.
- **Demo** — [`demo/aad_reference_agent/`](../../demo/aad_reference_agent/):
  the copy-paste path — implement a surface, mount the adapter, run.
- **Schema + test** — the committed `config/agent_surface/aad-v1.0.schema.json`
  (generated from the model) and `tests/integration/test_aad_conformance.py`
  (a CI gate proving an agent onboards before it ships).

## Make a service an agent (3 steps)

```python
from backend.agent_surface import AgentCard, AgentReply, AgentSurface
from aad import build_aad_router   # the AAD adapter

class MyService(AgentSurface):
    def card(self):   return AgentCard(slug="my-svc", name="My Service")
    def ask(self, q): return AgentReply(answer=do_real_work(q))
    def health(self): return {"status": "ok"}

app.include_router(build_aad_router(MyService()))   # now discoverable
```

## Versioning

`aad_version` is `MAJOR.MINOR`. A **minor** is additive-only — a reader that
knows an older minor ignores unknown fields, so old descriptors keep onboarding.
A **major** is breaking. A shipped field is never renamed or repurposed. The
committed JSON Schema is generated from the model (`make agent-surface-schema`)
so the published contract can't silently drift from the code.

## Auth

A descriptor declares *that* auth is required (`auth.kind`), **never the
secret** — the secret stays on the consumer side. `auth.kind: none` is a **dev**
default; a production agent must declare real auth before it is exposed. (This
mirrors the upstream auth-before-prod decision the AAD format came from.)

## Out of scope for this template

*Discovering* other agents — fetching arbitrary descriptor URLs, the SSRF/
trusted-host allowlist, redirect refusal, cross-version normalization — is the
**consumer** (platform) side. A template-derived service only **serves** its own
descriptor; do not vendor a discovery client here.
'''

_AGENT_SURFACE_ADR = r'''---
title: "ADR-0002: A vendor-neutral agent surface, with AAD as the first adapter"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, agent, surface, aad, discovery]
summary: Services become discoverable agents via a neutral AgentSurface contract; AAD is one thin wire adapter, not the standard.
id: docs-adr-0002-agent-surface
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# ADR-0002: A vendor-neutral agent surface, with AAD as the first adapter

**Status:** accepted

## Context
A chat/agent platform wants to onboard a template-derived service as an agent
from a single base URL, with no per-agent platform code. A proven format for
this exists upstream — the **Aion Agent Descriptor (AAD)**: a service serves a
versioned JSON descriptor at `/.well-known/aion-agent.json`, the platform
fetches it and registers the agent. (Upstream: Aion Chat ADR-0009 defines the
AAD format and its versioning; ADR-0008 makes real auth a prerequisite before
any agent is exposed to production.)

The naïve adoption — "make AAD the standard agent surface of the template" —
**violates this template's cardinal, enforced rule**: *state features
vendor-neutrally; name the neutral concept first; a vendor is one interchangeable
option confined to a thin adapter* (root `AGENT.md`, checked by
`scripts/check_structure.py`). AAD is one vendor's (Aion Chat's) wire dialect.
Baking it in as "the standard" is exactly what `models/` refuses for a model
provider and what triggers refuse for cron-vs-systemd.

## Decision
Adopt the **capability**, invert the **framing**.

1. **Neutral concept = an "agent surface."** A service reachable as an agent
   self-describes (`card`), answers (`ask`), and reports liveness (`health`).
   This is the `AgentSurface` protocol + neutral `AgentCard`/`AgentReply` in
   `src/backend/agent_surface/`. It carries no wire format, version envelope, or
   well-known path. This is the standard.
2. **AAD is the first adapter, in the transport layer.** `api/rest_fastapi/aad/`
   renders any `AgentSurface` into the AAD descriptor + endpoints (FastAPI emits
   `/openapi.json` for free). The vendor name lives only here. A second dialect
   (A2A, MCP-native, plugin manifest) is a sibling adapter over the same
   surface, registered alongside — never an edit to the contract.
3. **Copy-paste demo + CI conformance.** `demo/aad_reference_agent/` is the
   runnable "implement a surface, mount the adapter" path. The committed
   `config/agent_surface/aad-v1.0.schema.json` is **generated** from the model
   (`scripts/agent_surface/generate_aad_schema.py`), and
   `tests/integration/test_aad_conformance.py` proves a service onboards
   (descriptor validates against the committed schema; the `ask` binding
   resolves against the agent's own OpenAPI).
4. **In-process agents stay `function`.** Brains the host imports (no port/URL)
   are not discovered and not given a descriptor — discovery is for
   boundary-crossing services only. The module is opt-in.
5. **Serve, don't discover.** A template service only *serves* its own
   descriptor. The consumer-side discovery stack (URL fetch, SSRF/trusted-host
   allowlist, redirect refusal, version normalization) is the platform's
   concern and is deliberately **not** vendored here.

## Consequences
- Becoming a discoverable agent = implement three methods + mount one router.
  Adding a new wire dialect is a new adapter, not a re-plumb — the neutral
  contract is paid for at N=1 (as `models/` ships one backend behind an ABC).
- The published schema is generated, so the wire contract can't drift from the
  code; a `--check` mode guards it in pre-commit/CI.
- Auth: descriptors declare `auth.kind` only (never the secret). `none` is
  dev-only; production must declare real auth before exposure (per upstream
  ADR-0008).
- The template gains FastAPI/pydantic as the reference adapter's deps — already
  present for `api/rest_fastapi/`. The conformance test degrades gracefully
  where `jsonschema` is absent (structural checks still run).

## Alternatives considered
- **Make AAD the standard (the original proposal).** Rejected: inverts the
  template's enforced vendor-neutrality rule and couples a generic scaffold to
  one platform.
- **Raw OpenAPI as the descriptor, no neutral card.** Rejected: OpenAPI carries
  no card (icon, tagline, capabilities) and no "which field is the answer"
  semantics; you'd need `x-` extensions everywhere.
- **Ship the discovery consumer too.** Rejected as out of scope: a template
  serves a descriptor; it does not fetch others'.
'''

_AAD_CONFORMANCE_TEST = r'''"""Integration: the AAD reference agent is conformant and self-consistent.

Runs the reference agent in-process (TestClient), then proves three things
WITHOUT importing any consumer's discovery stack (a template only *serves* a
descriptor — it does not fetch others'):

  1. the served descriptor validates against the committed JSON Schema
     (`config/agent_surface/aad-v1.0.schema.json`, generated from the model);
  2. the descriptor's `ask` operationId resolves against the agent's OWN
     FastAPI-generated `/openapi.json` (a tiny vendored resolver, ~12 lines);
  3. the resolved endpoint actually answers, with the field names the
     descriptor's `io` map declared.
"""
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from demo.aad_reference_agent import DESCRIPTOR, app  # noqa: E402

pytestmark = pytest.mark.integration

_SCHEMA_PATH = _ROOT / "config" / "agent_surface" / "aad-v1.0.schema.json"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def served_descriptor(client: TestClient) -> dict:
    r = client.get("/.well-known/aion-agent.json")
    assert r.status_code == 200
    return r.json()


def _resolve_ask(descriptor: dict, openapi: dict) -> tuple:
    """Vendored resolver: descriptor.ask.operationId -> (METHOD, path) in the
    agent's own OpenAPI. Decoupled from any platform's discover()."""
    op_id = descriptor["transport"]["openapi"]["operations"]["ask"]["operationId"]
    for path, methods in openapi["paths"].items():
        for method, op in methods.items():
            if op.get("operationId") == op_id:
                return method.upper(), path
    raise AssertionError("ask operationId %r not in /openapi.json" % op_id)


def test_served_descriptor_matches_exported(served_descriptor: dict):
    """What the agent serves is exactly the DESCRIPTOR it exports."""
    assert served_descriptor == DESCRIPTOR


def test_descriptor_structural(served_descriptor: dict):
    """Always-on sanity (no jsonschema dep): required keys, version, slug shape."""
    for key in ("aad_version", "agent", "transport"):
        assert key in served_descriptor, "missing required key %r" % key
    assert served_descriptor["aad_version"] == "1.0"
    assert _SLUG_RE.match(served_descriptor["agent"]["slug"])
    assert served_descriptor["transport"]["protocol"] in ("openapi", "mcp")


def test_descriptor_validates_against_committed_schema(served_descriptor: dict):
    """The descriptor conforms to the committed, generated JSON Schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(served_descriptor, schema)


def test_dotless_fallback_is_served(client: TestClient):
    """Servers that can't serve a dot-directory get the `/aion-agent.json` fallback."""
    assert client.get("/aion-agent.json").status_code == 200


def test_ask_binding_resolves_and_answers(client: TestClient, served_descriptor: dict):
    """The ask operationId resolves in the agent's own OpenAPI and the endpoint answers."""
    method, path = _resolve_ask(served_descriptor, app.openapi())
    assert method == "POST"
    io = served_descriptor["transport"]["openapi"]["operations"]["ask"]["io"]
    r = client.request(method, path, json={io["question"]: "ping"})
    assert r.status_code == 200
    body = r.json()
    assert io["answer"] in body
    assert "ping" in body[io["answer"]]


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_malformed_slug_is_rejected_at_render():
    """An author-supplied slug that breaks the AAD pattern fails fast at render,
    rather than being served as a non-conformant descriptor."""
    import pydantic

    from aad import card_to_aad  # api/rest_fastapi is on sys.path via the demo import
    from backend.agent_surface import AgentCard

    with pytest.raises(pydantic.ValidationError):
        card_to_aad(AgentCard(slug="INVALID_SLUG", name="x"))
'''


def agent_surface():
    """Vendor-neutral agent surface + the AAD adapter (one dialect), demo,
    generated schema, generator, conformance docs (CONVENTIONS §14)."""
    w('src/backend/agent_surface/_models.py', _AS_MODELS_SRC)
    w('src/backend/agent_surface/contracts.py', _AS_CONTRACTS_SRC)
    w('src/backend/agent_surface/__init__.py', _AS_INIT_SRC)
    w('api/rest_fastapi/aad/descriptor.py', _AAD_DESCRIPTOR_SRC)
    w('api/rest_fastapi/aad/router.py', _AAD_ROUTER_SRC)
    w('api/rest_fastapi/aad/__init__.py', _AAD_INIT_SRC)
    w('api/rest_fastapi/aad/README.md', _AAD_README)
    w('api/rest_fastapi/aad/AGENT.md', _AAD_AGENT)
    w('config/agent_surface/aad-v1.0.schema.json', _AAD_SCHEMA_JSON)
    w('scripts/agent_surface/generate_aad_schema.py', _AAD_GEN_SRC)
    w('demo/aad_reference_agent/app.py', _AAD_DEMO_APP_SRC)
    w('demo/aad_reference_agent/__init__.py', _AAD_DEMO_INIT_SRC)
    w('demo/aad_reference_agent/README.md', _AAD_DEMO_README)
    w('demo/aad_reference_agent/AGENT.md', _AAD_DEMO_AGENT)
    w('docs/guides/agent-surface.md', _AGENT_SURFACE_GUIDE)
    w('docs/adr/0002-agent-surface-and-discovery.md', _AGENT_SURFACE_ADR)
    w('tests/integration/test_aad_conformance.py', _AAD_CONFORMANCE_TEST)
    symlink_claude('api/rest_fastapi/aad')
    symlink_claude('demo/aad_reference_agent')
# === END agent_surface ===


# --------------------------------------------------------------------------- #
def main():
    print(f"Scaffolding into: {BASE}")
    root_files()
    hidden_files()
    quality_tooling()
    src_tree()
    tests_tree()
    test_docs_tree()
    docs_tree()
    peripheral_dirs()
    api_examples()
    automation_examples()
    tooling_adapters()
    wiki_agents()
    agent_surface()
    print("Done.")


if __name__ == "__main__":
    main()
