# SupportPrompt Lab

SupportPrompt Lab is a production-style prompt engineering portfolio for fictional
e-commerce support workflows. The service is built with FastAPI, Pydantic, PostgreSQL,
SQLAlchemy, and Alembic.

## Run with Docker Compose

Docker Compose starts PostgreSQL, waits for it to become healthy, applies Alembic
migrations, and then starts the API:

```bash
cp .env.example .env
docker compose up --build
```

The API documentation is available at <http://127.0.0.1:8000/docs>. Use
<http://127.0.0.1:8000/health> for process liveness and
<http://127.0.0.1:8000/ready> for database readiness.

Stop the services without deleting database data:

```bash
docker compose down
```

## Run locally

Local development requires [`uv`](https://docs.astral.sh/uv/) and PostgreSQL.

## Setup

```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn support_prompt_lab.main:app --reload
```

Run the database integration test while PostgreSQL is available:

```bash
RUN_DATABASE_INTEGRATION_TESTS=1 uv run pytest -m integration
```

## Quality checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv run pre-commit run --all-files
```

Install the Git hooks once per clone:

```bash
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

The pre-commit hook formats and lints changed Python files and runs mypy. The pre-push
hook runs the test suite.
