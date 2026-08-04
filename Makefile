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

.PHONY: help new check-python check check-all check-corpus check-openapi check-aad advise check-generic verify test unit integration e2e smoke \
        lint lint-py lint-fe fmt typecheck typecheck-py typecheck-fe \
        fe-install run run-api run-web site-data site-static demo agent-surface-schema

help: ## List tasks
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n",$$1,$$2}'

check-python: ## Fail early with a clear message if PY is older than pyproject requires
	$(PY) scripts/check_python_version.py

# `new` hands copier an ABSOLUTE template path on purpose: copier stores that
# argument verbatim as `_src_path` in the generated project, and a relative one is
# re-resolved against the *project* on `copier update` — copier then clones the
# project as if it were the template and git dies on `pathspec ... did not match`.
# The dirty-tree refusal is the same contract from the other end: from a dirty
# template copier records a WIP commit that exists only in its throwaway clone, so
# the generated project could never resolve `_commit` either. Both are pinned by
# tests/integration/test_copier_generator_contract.py.
new: ## Generate a NEW project from this template into DEST (interactive Q&A). Needs the 'template' extra.
	@test -n "$(DEST)" || { echo "usage: make new DEST=../my-new-project"; exit 2; }
	@test -n "$(ALLOW_DIRTY)" || test -z "$$(git status --porcelain 2>/dev/null)" || { \
		echo "refusing: keel's tree is dirty, so copier would record a WIP commit that"; \
		echo "exists only in its throwaway clone and '$(DEST)' could never update from"; \
		echo "it. Commit or stash first, or re-run with ALLOW_DIRTY=1."; exit 2; }
	$(PY) -m copier copy "$(abspath .)" "$(DEST)"

check: ## Validate structure + frontmatter (3.6-safe)
	$(PY) scripts/check_structure.py

check-all: check check-corpus check-openapi check-aad ## All deterministic checks (project interpreter; see docs/guides/deterministic-checks.md)
check-corpus: check-python ## Corpus integrity + build determinism (needs the project interpreter)
	$(PY) scripts/jobs/check_corpus.py
check-openapi: ## Committed openapi.json in sync with the app (skips if FastAPI absent)
	$(PY) api/rest_fastapi/export_openapi.py --check
check-aad: ## Committed AAD schema in sync with the model (skips if pydantic absent)
	$(PY) scripts/agent_surface/generate_aad_schema.py --check

advise: ## Advisory: flag overfitting / answer-key + coding-practice smells (CONVENTIONS §18; never fails the build)
	-$(PY) scripts/check_generic.py
	-$(PY) scripts/check_practices.py
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

lint: lint-py lint-fe ## Lint everything (Python + frontend)
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
site-data: ## Rebuild the corpus + agent llms.txt the showcase reads
	$(PY) scripts/jobs/build_corpus.py
	$(PY) scripts/jobs/link_corpus.py
	$(PY) scripts/jobs/build_llms_txt.py
site-static: site-data ## Snapshot the showcase to static files (no backend) for a static/GitHub Pages build
	$(PY) scripts/jobs/export_showcase_static.py --base-url "$(BASE_URL)"
run-api: ## Serve the showcase REST API (uvicorn :8000; needs the project interpreter)
	$(PY) -m uvicorn app:app --app-dir api/rest_fastapi --reload --port 8000
run-web: ## Serve the showcase frontend (Astro); proxies /api to the backend
	cd src/frontend/astro && API_PROXY_TARGET=$${API_PROXY_TARGET:-http://localhost:8000} npm run dev
demo: ## Run the demo
	$(PY) demo/run_demo.py
agent-surface-schema: ## Regenerate the committed AAD JSON Schema from the model
	$(PY) scripts/agent_surface/generate_aad_schema.py
