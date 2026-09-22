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

## Versioned prompts

Production prompts live under `prompts/<name>/<semantic-version>/`. The registry
validates metadata and version sequences, then selects either an exact version, a
strategy variant, or the latest compatible prompt:

```python
from pathlib import Path

from support_prompt_lab.prompts import PromptRegistry

registry = PromptRegistry(Path("prompts"))
rendered = registry.render(
    "triage",
    {"ticket_text": "My order has not arrived."},
    strategy="few_shot",
)
```

The registry validates and compiles templates once at startup. Rendering rejects
missing or unexpected variables; every declared value must be XML-delimited and use
the `xml_escape` filter. The included `triage` prompt provides zero-shot, few-shot,
and many-shot variants at versions `1.0.0`, `1.1.0`, and `1.2.0`.

## Promptfoo baseline

The baseline evaluation calls the complete `POST /v1/tickets/analyze` workflow using
the golden tickets in `evaluations/datasets/`. It requires Node.js 22.22 or newer and
a running API configured with `OPENAI_API_KEY` and `OPENAI_MODEL`.

Install the pinned development dependency and validate the configuration without
making model calls:

```bash
npm ci
npm run eval:validate
```

Start the API, then run the baseline against its default local address:

```bash
npm run eval:baseline
```

Override the target when the API runs elsewhere:

```bash
SUPPORT_PROMPT_LAB_BASE_URL=http://localhost:9000 npm run eval:baseline
```

The baseline invokes the configured live model and can incur API charges.
