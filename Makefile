PYTHON ?= python3
BASE_URL ?= http://127.0.0.1:8000
DEMO_ARGS ?=
UV_CACHE_DIR ?= .tools/uv-cache

export UV_CACHE_DIR

.PHONY: start stop logs demo demo-check quality test eval-validate eval-release

.env:
	cp .env.example .env
	@echo "Created .env. Add OPENAI_API_KEY and OPENAI_MODEL before model-backed requests."

start: .env
	docker compose up --build --wait

stop:
	docker compose down

logs:
	docker compose logs --follow api

demo: start
	$(PYTHON) scripts/demo.py --base-url "$(BASE_URL)" $(DEMO_ARGS)

demo-check:
	$(PYTHON) scripts/demo.py --dry-run $(DEMO_ARGS)

test:
	uv run pytest

quality:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest
	npm run eval:test-assertions
	npm run eval:test-reports

eval-validate:
	npm run eval:validate:all

eval-release:
	npm run eval:release
