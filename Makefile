# Task runner. `make help` lists targets.
.DEFAULT_GOAL := help
PY ?= python3
# Make src/ importable as top-level packages for ad-hoc runs (tests set their own
# sys.path too; this just means `PY -c 'import backend'` works from the repo root).
PYTHONPATH ?= src:.

# Frontend apps = any src/frontend/* that has a package.json. The FE
# gates iterate over whatever exists, so they are framework-agnostic and
# a no-op on backend-only repos.
FE_APPS := $(dir $(wildcard src/frontend/*/package.json))

# Every Python root the gate must see. MUST equal CODE_ROOTS in
# scripts/check_structure.py — that list is the repo's single declaration of
# "where Python lives", and the structural checks already walk it. Keeping the
# lint/format scope narrower than it is how `make verify` came to report green
# over most of the repo; tests/integration/test_gate_scope.py imports the list
# from check_structure.py and fails if these two drift apart.
CODE_ROOTS := src tests api models mcp agents demo scripts runtimes
# ...filtered to what actually exists: ruff exits 1 with `E902 No such file or
# directory` on a missing path, and copier prunes directories from a generated
# project (frontend stack, add-on transports), so a literal list would hard-fail
# downstream instead of linting what shipped.
PY_ROOTS := $(wildcard $(CODE_ROOTS))

.PHONY: help new check-python check check-all check-corpus check-openapi check-aad check-cdmon advise check-generic verify test unit integration e2e smoke \
        lint lint-py lint-fe fmt fmt-check typecheck typecheck-py typecheck-fe \
        fe-install run run-api run-web site-data site-static demo agent-surface-schema

help: ## List tasks
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-22s %s\n",$$1,$$2}'

check-python: ## Fail early with a clear message if PY is older than pyproject requires
	$(PY) scripts/check_python_version.py

# Which template revision `make new` generates from. Explicit ON PURPOSE: given no
# --vcs-ref copier resolves `self.ref or get_latest_tag(...)`, i.e. the newest TAG —
# so the day keel is tagged, `make new` would silently stop generating from the
# checkout the user is looking at. Override to smoke-test a release: VCS_REF=v0.1.0.
VCS_REF ?= HEAD

# Three ways `make new` can hand back a project that can never `copier update`, all
# refused below and all pinned by tests/integration/test_copier_generator_contract.py:
#   1. a RELATIVE template path — copier stores the argument verbatim as `_src_path`,
#      and a relative one is re-resolved against the *project* on update: copier
#      clones the project as if it were the template and git dies on
#      `pathspec ... did not match`. Hence $(abspath .).
#   2. NOT A GIT CHECKOUT (a ZIP download, an `rsync --exclude=.git` copy) — copier
#      records no `_commit` at all. ALLOW_DIRTY deliberately does not override this:
#      it is an escape hatch for uncommitted work, and no amount of it makes a
#      non-repo resolvable.
#   3. a DIRTY tree — with ref=HEAD copier stages the working tree into its throwaway
#      clone and commits it (copier/_vcs.py), so `_commit` names a sha no clone of
#      keel has ever seen. ALLOW_DIRTY=1 overrides, for template authors iterating.
new: ## Generate a NEW project from this template into DEST (interactive Q&A). Needs the 'template' extra.
	@test -n "$(DEST)" || { echo "usage: make new DEST=../my-new-project"; exit 2; }
	@git rev-parse --git-dir >/dev/null 2>&1 || { \
		echo "refusing: this keel is not a git checkout, so copier records no _commit"; \
		echo "and '$(DEST)' could never run 'copier update'. Clone the repo instead of"; \
		echo "downloading/copying it without .git."; exit 2; }
	@test -n "$(ALLOW_DIRTY)" || test -z "$$(git status --porcelain)" || { \
		echo "refusing: keel's tree is dirty, so copier would record a WIP commit that"; \
		echo "exists only in its throwaway clone and '$(DEST)' could never update from"; \
		echo "it. Commit or stash first, or re-run with ALLOW_DIRTY=1."; exit 2; }
	$(PY) -m copier copy --vcs-ref "$(VCS_REF)" "$(abspath .)" "$(DEST)"

check: ## Validate structure + frontmatter (3.6-safe)
	$(PY) scripts/check_structure.py

check-all: check check-corpus check-openapi check-aad check-cdmon ## All deterministic checks (project interpreter; see docs/guides/deterministic-checks.md)
check-corpus: check-python ## Corpus integrity + build determinism (needs the project interpreter)
	$(PY) scripts/jobs/check_corpus.py
check-openapi: ## Committed openapi.json in sync with the app (skips if FastAPI absent)
	$(PY) api/rest_fastapi/export_openapi.py --check
check-aad: ## Committed AAD schema in sync with the model (skips if pydantic absent)
	$(PY) scripts/agent_surface/generate_aad_schema.py --check
check-cdmon: ## cdmon code-doc drift (a stated skip until cdmon and config/cdmon/cdmon.yaml exist)
	$(PY) scripts/cdmon_sync.py --check

advise: ## Advisory: overfitting / answer-key + coding-practice smells, and unowned corpus nodes (CONVENTIONS §18; never fails the build)
	-$(PY) scripts/check_generic.py
	-$(PY) scripts/check_practices.py
	-$(PY) scripts/accountability_report.py
check-generic: advise ## Alias for `advise` (the generic-solution + practice advisor)

verify: check-all lint typecheck test ## Run all gates (all checks + lint + types + tests)

test: check-python ## Run the whole test suite
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest

unit: ## Run unit tests only
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -m unit
integration: ## Run integration tests
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -m integration
e2e: ## Run end-to-end tests
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -m e2e
smoke: ## Run smoke tests
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -m smoke

lint: lint-py fmt-check lint-fe ## Lint everything (Python + frontend + formatting)
lint-py: ## Lint Python (ruff, via the selected interpreter)
	$(PY) -m ruff check $(PY_ROOTS)
# Each recipe LINE is its own shell, so a bare `... || exit 0` guard on its own line
# ends only that shell and make happily runs the loop below it — the guard printed
# "skipping" and the target then died on `npm: command not found`. Guard and loop are
# therefore ONE logical line. FE_APPS is tested first so a backend-only project (copier
# prunes src/frontend for `frontend_stack: none`) is silent rather than told about npm.
# tests/integration/test_gate_scope.py pins all four cells, including that a genuinely
# failing FE script still fails the target.
lint-fe: ## Lint frontend apps (ESLint) — generic to any FE framework
	@test -n "$(strip $(FE_APPS))" || exit 0; \
	command -v npm >/dev/null 2>&1 || { echo "npm not found; skipping frontend lint"; exit 0; }; \
	for app in $(FE_APPS); do \
		if [ -d "$$app/node_modules" ]; then echo "eslint: $$app"; (cd $$app && npm run --silent lint) || exit 1; \
		else echo "skip $$app (no node_modules — run 'make fe-install')"; fi; \
	done

fmt: ## Format Python (ruff, via the selected interpreter)
	$(PY) -m ruff format $(PY_ROOTS)
# The gate half of `fmt`. Formatting is the one readability rule a machine can
# decide with no judgment at all, so it belongs in `lint` rather than in review;
# a fix-it command nobody is required to run is decorative (measured: 109 files
# had drifted while `make verify` stayed green). Read-only ON PURPOSE — a check
# that writes is not a check, and CI must report drift, not silently repair it.
fmt-check: ## Check Python formatting without writing (rides `make lint`)
	$(PY) -m ruff format --check $(PY_ROOTS)

typecheck: typecheck-py typecheck-fe ## Type-check everything (Python + frontend)
# No paths on the command line ON PURPOSE: an explicit path argument OVERRIDES
# `[tool.mypy] files`, so passing `src` here would silently re-narrow the gate to
# `src` no matter how wide the config's scope (and its ratchet) got.
typecheck-py: ## Type-check Python (mypy, scope from pyproject [tool.mypy] files)
	$(PY) -m mypy
# Same one-logical-line guard as lint-fe above; see the comment there.
typecheck-fe: ## Type-check frontend apps (tsc / astro check)
	@test -n "$(strip $(FE_APPS))" || exit 0; \
	command -v npm >/dev/null 2>&1 || { echo "npm not found; skipping frontend typecheck"; exit 0; }; \
	for app in $(FE_APPS); do \
		if [ -d "$$app/node_modules" ]; then echo "typecheck: $$app"; (cd $$app && npm run --silent typecheck) || exit 1; \
		else echo "skip $$app (no node_modules — run 'make fe-install')"; fi; \
	done

fe-install: ## Install frontend deps for all FE apps
	@for app in $(FE_APPS); do echo "npm install: $$app"; (cd $$app && npm install) || exit 1; done

run: ## Run the app composition root
	$(PY) -m app
# The corpus is NOT showcase-owned — mcp/qa_server.py, scripts/query_corpus.py and
# three of the four agents read it — so it is built in every project. llms.txt renders
# the showcase READ MODEL, so its renderer is pruned along with the showcase
# (copier.yml `showcase`), and this says so instead of dying on a missing script.
site-data: ## Rebuild the corpus (+ agent llms.txt where the showcase ships)
	$(PY) scripts/jobs/build_corpus.py
	$(PY) scripts/jobs/link_corpus.py
	@if [ -f scripts/jobs/build_llms_txt.py ]; then $(PY) scripts/jobs/build_llms_txt.py; \
	else echo "skip llms.txt (this project declined the showcase)"; fi
# --out-dir comes from the SAME discovery as run-web/lint-fe (FE_APPS), so the
# snapshot lands in whichever frontend actually shipped. Keel declares no single
# `layers.frontend.stack` (it carries both reference stacks for the showcase), so the
# script's own manifest-derived default cannot resolve here — supplying it from the
# wildcard keeps one discovery rule for the whole Makefile. Empty FE_APPS (a
# backend-only project) passes no flag at all and the script skips itself.
site-static: site-data ## Snapshot the showcase to static files (no backend) for a static/GitHub Pages build
	@if [ -f scripts/jobs/export_showcase_static.py ]; then \
		$(PY) scripts/jobs/export_showcase_static.py --base-url "$(BASE_URL)" \
			$(if $(strip $(FE_APPS)),--out-dir "$(firstword $(FE_APPS))public"); \
	else echo "skip static snapshot (this project declined the showcase)"; fi
run-api: ## Serve the showcase REST API (uvicorn :8000; needs the project interpreter)
	$(PY) -m uvicorn app:app --app-dir api/rest_fastapi --reload --port 8000
# The frontend directory is DISCOVERED (FE_APPS), never named: copier prunes the
# un-chosen stack, so a literal `src/frontend/astro` here was ENOENT in every
# project that did not answer "astro" — including the default one. Pinned by
# tests/integration/test_copier_generation.py.
run-web: ## Serve the showcase frontend (dev server); proxies /api to the backend
	@test -n "$(strip $(FE_APPS))" || { echo "no frontend app under src/frontend (backend-only project)"; exit 2; }
	cd $(firstword $(FE_APPS)) && API_PROXY_TARGET=$${API_PROXY_TARGET:-http://localhost:8000} npm run dev
demo: ## Run the demo
	$(PY) demo/run_demo.py
agent-surface-schema: ## Regenerate the committed AAD JSON Schema from the model
	$(PY) scripts/agent_surface/generate_aad_schema.py
