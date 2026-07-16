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

.PHONY: help scaffold check-python check check-all check-corpus check-openapi check-aad scaffold-sync scaffold-parity advise check-generic verify test unit integration e2e smoke \
        lint lint-py lint-fe fmt typecheck typecheck-py typecheck-fe \
        fe-install run run-api run-web site-data site-static demo agent-surface-schema

help: ## List tasks
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n",$$1,$$2}'

check-python: ## Fail early with a clear message if PY is older than pyproject requires
	$(PY) scripts/check_python_version.py

scaffold: ## (Re)generate the skeleton (README/CLAUDE/exemplars)
	$(PY) scripts/scaffold.py

check: ## Validate structure + frontmatter + scaffold embeds (3.6-safe)
	$(PY) scripts/check_structure.py
	$(PY) scripts/check_scaffold_sync.py --check

check-all: check check-corpus check-openapi check-aad ## All deterministic checks (project interpreter; see docs/guides/deterministic-checks.md)
check-corpus: check-python ## Corpus integrity + build determinism (needs the project interpreter)
	$(PY) scripts/jobs/check_corpus.py
check-openapi: ## Committed openapi.json in sync with the app (skips if FastAPI absent)
	$(PY) api/rest_fastapi/export_openapi.py --check
check-aad: ## Committed AAD schema in sync with the model (skips if pydantic absent)
	$(PY) scripts/agent_surface/generate_aad_schema.py --check
scaffold-sync: ## scaffold.py embeds match the live scripts (3.6-safe)
	$(PY) scripts/check_scaffold_sync.py --check
scaffold-parity: ## Prove the copier template reproduces every scaffold.py artifact (needs the 'template' extra)
	$(PY) scripts/scaffold_parity.py

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
	$(PY) -m ruff check src tests
lint-fe: ## Lint frontend apps (ESLint) — generic to any FE framework
	@command -v npm >/dev/null 2>&1 || { echo "npm not found; skipping frontend lint"; exit 0; }
	@for app in $(FE_APPS); do \
		if [ -d "$$app/node_modules" ]; then echo "eslint: $$app"; (cd $$app && npm run --silent lint) || exit 1; \
		else echo "skip $$app (no node_modules — run 'make fe-install')"; fi; \
	done

fmt: ## Format Python (ruff, via the selected interpreter)
	$(PY) -m ruff format src tests

typecheck: typecheck-py typecheck-fe ## Type-check everything (Python + frontend)
typecheck-py: ## Type-check Python (mypy, via the selected interpreter)
	$(PY) -m mypy src
typecheck-fe: ## Type-check frontend apps (tsc / astro check)
	@command -v npm >/dev/null 2>&1 || { echo "npm not found; skipping frontend typecheck"; exit 0; }
	@for app in $(FE_APPS); do \
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
