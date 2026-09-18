# SupportPrompt Lab

SupportPrompt Lab is a production-style prompt engineering portfolio for fictional
e-commerce support workflows. The service is built with FastAPI, Pydantic, PostgreSQL,
SQLAlchemy, and Alembic.

## Prerequisites

- macOS or Linux
- [`uv`](https://docs.astral.sh/uv/)
- PostgreSQL

## Setup

```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn support_prompt_lab.main:app --reload
```

The API documentation is available at <http://127.0.0.1:8000/docs>, and the process
health endpoint is available at <http://127.0.0.1:8000/health>.

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
