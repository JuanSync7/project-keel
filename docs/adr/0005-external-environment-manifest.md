---
title: "ADR-0005: Declare the external environment in config/environment.json — Docker's contract, applied to what you cannot containerize"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, environment, external-dependency, versioning, reproducibility, modules, container, provider]
summary: Externals (binaries, env vars, licence servers, mounts, sibling repos, modules) become typed records in config/environment.json; a deterministic check proves the declaration is complete, a prober measures the live host, and a lock plus fingerprint make a result attributable to the environment that produced it.
id: docs-adr-0005-external-environment-manifest
created: 2026-08-04
updated: 2026-09-02
visibility: internal
canonical: true
---

# ADR-0005: Declare the external environment (`config/environment.json`)

**Status:** proposed

## Context

Keel has a manifest for **what is inside** the repo (`config/project.json`,
§15), for **which rules apply** (`config/practices.json`, §18), and for **what
the API surface is** (the committed `openapi.json` and AAD schema, §14). It has
nothing for **what is outside** — and "outside" is the category that is least
reproducible, most silently drifting, and most likely to make a result
unexplainable six months later.

Today the answer to *"what does this project need from the host?"* is: read the
`Makefile`, grep for `os.environ`, and hope. The repo demonstrates the failure
mode on itself — the following are read or executed by shipped code and declared
nowhere:

| External | Read at | Declared |
|----------|---------|----------|
| `KEEL_MCP_MODEL` | `mcp/qa_server.py` | no |
| `OPENAI_API_KEY` | `models/openai_compatible.py` | no |
| 3 `import.meta.env.*` + 3 `process.env.*` vars | `src/frontend/**` | no |
| `claude` binary | `models/claude_code_headless.py` | no |
| `cdmon` binary | `scripts/cdmon_sync.py` | no |
| `make` binary | `scripts/run_make_target.py` | no |
| `npm` / `node` | `Makefile` (`lint-fe`, `typecheck-fe`, `fe-install`) | no |

`.env.example` names two variables, neither of which is in that list. The one
external that *is* declared — the Python floor — has real machinery behind it
(`check_H` errors when `layers.backend.python` and `pyproject`'s `requires-python`
disagree, and `scripts/check_python_version.py` fails early with a clear message),
but it is hardcoded to that one pair: there is no way to declare a *second*
external the same way.

The motivating case is harder than a web stack. A silicon-design project pulls
in Environment Modules (`module load synopsys/vcs/2024.09-SP2`), site licence
servers, a Slurm farm, read-only PDK/IP trees on NFS automounts, and sibling
script libraries — none of which live in the repo, all of which are versioned,
and any of which silently changing invalidates a result.

## The container question (why this is not Docker in disguise)

It largely **is** Docker's idea, and this ADR does not compete with containers.
Where a container reaches, it is the better answer, and keel already has
`containers/` for it. State the boundary honestly:

**Containers win** on reproducible userland, pinned OS packages, pinned language
runtimes, and dev/CI parity. If a project can be fully described by a
`Dockerfile` plus lockfiles, it should be, and this manifest shrinks to a handful
of records.

**Containers do not reach** four things that matter here:

1. **Licensed, host-installed tooling.** A Synopsys/Cadence/Siemens install is
   tens to hundreds of GB on NFS, licence-server-bound, and not redistributable.
   You cannot bake VCS into an image you own.
2. **Activation inside a shared host.** `module load` happens in a *shell*, per
   job, on a farm node. An image pins its own contents; it cannot tell you which
   module version the shell that actually ran your regression had loaded. That
   is the exact failure this ADR targets.
3. **Things outside any image by definition.** Licence servers, NFS export
   identity, farm partitions and QoS, read-only PDK mounts, the host GPU driver,
   sibling repos pinned by ref.
4. **Partial adoption.** Real teams are containerized for CI and not the
   workstation, or the reverse. The manifest is the artifact that spans both.

**What we take from Docker is its three-artifact contract**, deliberately
copied rather than reinvented:

| Docker | Keel |
|--------|------|
| `Dockerfile` — intent, hand-written | `config/environment.json` |
| image digest `sha256:…` — the fact | `config/environment.lock.json` |
| `docker run` — activation | `scripts/env_plan.py --plan` |
| "same image → same result" | fingerprint stamped into results |

Accordingly, **`container` is one provider in the manifest, not a rival to it.**
Select it and `check-env` degenerates to *"does the running image digest match
the lock"* — cheap, and correct.

### When this is not worth much

Say this plainly so nobody builds machinery they do not need:

- A project fully described by `pyproject.toml` + a lockfile + a `Dockerfile`
  gets ~5 records and no profiles. That is the intended shape, not a failure.
- **An absent `config/environment.json` is a WARN, never an error.** Nothing
  forces adoption — the same safe degradation `check_H` already applies to an
  absent `project.json`.
- The part that pays for itself in *every* project regardless of exotica is
  the completeness scan (below). The version-constraint machinery is
  opt-in on top of it.

## Decision

Add a committed sibling manifest, `config/environment.json`, and split its
enforcement in two — because probing a host is not deterministic, and
`docs/guides/deterministic-checks.md` promises *"same inputs → same verdict, no
model, no network."*

**1. `config/environment.json` — the declaration.** Hand-edited JSON, read by
path with `json.load`, never imported: the same physical contract as
`practices.json` and `project.json`. Each external is one typed record:

```jsonc
{ "id": "vcs",
  "kind": "tool", "name": "synopsys/vcs", "tier": "required",
  "profile": "eda", "layer": "backend",
  "version": "==2024.09-SP2", "version_scheme": "opaque",
  "why": "RTL simulation + coverage for the verification flow.",
  "needed_by": ["scripts/jobs/run_regression.py"],
  "provider": "modules",
  "probe": {"how": "module", "modulepath_pin": true},
  "absent_effect": "Regression cannot run; results are unattributable." }
```

Profiles (`eda`, `web`, `cloud`) ship **defined but off** and are enabled from
`config/project.json`, reusing the defined-vs-enabled split and the
`_profile_flag_findings` helper that `practices.json` already established.

**2. A `check_*` letter in `check_structure.py` — deterministic, 3.6-safe, no probing.**
(Drafted as `check_O`, then `check_P`; each was taken by a check that landed
first — `O` by ADR-0008, `P` by Makefile help parity — and letters belong to
landed checks, so this proposal takes the next free letter on the day it lands
rather than reserving one.)
It validates the records' shape and closed vocabularies, and does the thing that
stops a manifest rotting into paperwork: **it discovers undeclared externals.**
Without it the manifest becomes the `owner:` field: elaborate, and unsatisfied on
444 of 500 corpus nodes because nothing ever forced it. This is the same species
of meta-gate as `check_M`.

Discovery runs over **three** sources, not one — a single Python AST walk reaches
only 3 of the 7 externals tabled above, and designing on that assumption would
ship the same false confidence this ADR is written against:

| Source | Finds | Misses |
|---|---|---|
| AST over `CODE_ROOTS` — literal `os.environ[…]`/`os.getenv`, `shutil.which`, `subprocess.run` with a literal `argv[0]` | `KEEL_MCP_MODEL`, `cdmon` | anything named indirectly |
| Regex over `src/frontend/**` for `process.env.X` / `import.meta.env.X` | the 6 frontend vars | — |
| **Text scan of `Makefile` + `.github/workflows/*.yml`** for `command -v X`, and recipe/`run:` argv heads | `npm`, `node` | — |

Three call sites are **statically undecidable** and must not be pretended away:
`models/openai_compatible.py:60` reads `os.environ.get(self.api_key_env)` (the
name is an attribute), and `models/claude_code_headless.py:30` and
`scripts/run_make_target.py:32` both call `subprocess.run(cmd, …)` on a variable.
So discovery has a second half — a **dynamic-call-site census**: every
`subprocess.run`/`os.environ.get` whose argument is not a literal is reported as
*a site the scan cannot see*, and must carry either a `# practice-ok` waiver or a
`needed_by` entry pointing at it from some record. That converts an invisible gap
into a visible, reviewable one, which is the most an offline check can honestly
claim. Both halves are errors; both are line-waivable with the existing pragma.

**3. `scripts/check_environment.py` — the host prober (`make check-env`).**
Stdlib-only and 3.6-safe on purpose: the hosts that most need it are the old
ones. One prober per closed `probe.how`, producing a gitignored
`wiki/environment-report.json` recording per record `{status, declared,
resolved, locked, evidence, remedy, impact}` — `evidence` a literal string so a
verdict is auditable rather than asserted. Not part of `make check`.

**4. `config/environment.lock.json` — the fact, and the fingerprint.** The
manifest's `version` is a *policy*; the lock is what a blessed host actually
resolved, per profile (`laptop` / `farm-node` / `ci` / `container`). Volatile
provenance (`measured_at`, host) is quarantined out of the hash. Two derived
values do the real work:

- `intent_digest` — sha256 of the canonicalized manifest, stored in the lock.
  A mismatch is an **offline** commit-time error, so "edited a constraint
  without re-locking" cannot reach CI. This is `check_M`'s self-binding property
  applied to the environment.
- `fingerprint` — sha256 over `{id: resolved_version}` for active records. Stamp
  the 12-char token into a regression log, a Slurm job record, or a build
  artifact, and a result becomes attributable to the toolchain that produced it.

**5. Version comparison is scheme-gated, defaulting to `opaque`.**
`2024.09-SP2`, `V-2023.12` and `T-2022.03-SP1` have no total order any generic
comparator gets right, so `opaque` supports only `==` and `in [...]`. A record
wanting `>=` must declare `pep440` or `semver` and own the consequence. This is
§18 ("solve the class of inputs") applied rather than quoted.

**6. Providers are a thin-adapter seam, per AGENT.md's first rule.**
*Environment provider* is the neutral concept; `modules`, `conda`, `spack`,
`nix`, `container` and plain `path` are interchangeable adapters behind an
`available()` / `probe()` / `activation()` contract, with the vocabulary in data.
`scripts/env_plan.py --plan` emits the activation lines for the active profile
reading JSON only and importing nothing — so it runs on a bare farm node
*before* any Python environment exists. On a 3.6.8 host that bootstrap ordering
is decisive.

At this site the `modules` adapter delegates resolution to the existing
`aion-module` generator (curated version registry, five gates, byte-identical
output) rather than reimplementing it. Keel declares intent; `aion-module`
resolves it; `check-env` verifies the shell that ran the job actually had it —
the gap neither tool sees alone.

## Consequences

- One new manifest, one new check, one new script, one new lock. No new
  top-level directory, so `TAXONOMY`, `CODE_ROOTS` and the §2 table are
  untouched.
- `.env.example` stops being hand-written prose and becomes a generated,
  drift-checked view of the `kind: env-var` records — the same
  generate-and-byte-compare contract as the AAD schema and `openapi.json`.
- The completeness scan will fail the repo on first run against the
  seven undeclared externals in the table above. That is the point; they are
  declared as part of landing it.
- **Prerequisite:** no gate currently knows the `.jinja` twins exist. A fifth
  twin must not be added before twin-parity is gated, or this change
  manufactures a new instance of the drift class it claims to fix. Ship the
  manifest untailored in v1; tailor it once parity is enforced.

## Alternatives considered

- **A `Dockerfile`/devcontainer and nothing else.** Rejected as the *sole*
  answer for the reasons above; adopted as one provider. For projects it fully
  covers, this ADR's footprint is ~5 records.
- **Nix or spack.** Excellent resolvers, but a resolver is not a declaration and
  neither is installable on a licensed-EDA farm. Both are candidate providers.
- **conda `environment.yml`.** Language-scoped; says nothing about licence
  servers, mounts or modules.
- **Document it in the README.** The status quo. It rots, and the repo already
  measures how fast: `owner:` is unsatisfied on 444 of 500 corpus nodes.
