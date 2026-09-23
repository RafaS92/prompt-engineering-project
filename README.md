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

`POLICY_DECISION_SAMPLE_COUNT` configures independent policy-decision samples. It
defaults to `1` and accepts the bounded odd values `1`, `3`, or `5`.
`PolicyConsensusStage` runs the existing validated policy stage that many times and
returns both the sample executions and their deterministic consensus result. A strict
majority continues through the workflow; a tie deterministically escalates to a human
and skips response drafting. The API exposes the rationale-free result under
`policy.consensus`, and reported policy token usage is summed across all samples.

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
the `xml_escape` filter. The prompt library retains every immutable zero-, few-, and
many-shot version. The runtime default is configured independently with
`TRIAGE_PROMPT_STRATEGY`, which defaults to `zero_shot`.

## Promptfoo baseline

The baseline evaluation calls the complete `POST /v1/tickets/analyze` workflow using
the golden tickets in `evaluations/datasets/`. It requires Node.js 22.22 or newer and
a running API configured with `OPENAI_API_KEY` and `OPENAI_MODEL`.

Install the pinned development dependency and validate the configuration without
making model calls:

```bash
npm ci
npm run eval:test-assertions
npm run eval:test-reports
npm run eval:validate
npm run eval:validate:triage
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

To compare the triage prompt variants over the same golden tickets, run:

```bash
npm run eval:compare:triage
```

This sends each case through zero-shot `1.6.0`, few-shot `1.4.0`, and many-shot
`1.5.0`. It writes JSON and HTML reports to `evaluations/reports/`, which is ignored
by Git. The API's optional `triage_prompt` request field accepts either a `strategy`
or semantic `version`; omitting it uses the configured default strategy.

To compare policy self-consistency, start three API processes configured with the
same model and sample counts `1`, `3`, and `5` respectively:

```bash
POLICY_DECISION_SAMPLE_COUNT=1 uv run uvicorn support_prompt_lab.main:app --port 8011
POLICY_DECISION_SAMPLE_COUNT=3 uv run uvicorn support_prompt_lab.main:app --port 8013
POLICY_DECISION_SAMPLE_COUNT=5 uv run uvicorn support_prompt_lab.main:app --port 8015
```

Run each command in a separate terminal. Then validate and execute the comparison:

```bash
npm run eval:validate:policy-consensus
npm run eval:compare:policy-consensus
```

Promptfoo sends every case in `ambiguous_policy_tickets.yaml` to all three API
instances and verifies the reported sample count and vote consistency. Override the
default endpoints with `SUPPORT_PROMPT_LAB_SAMPLE_1_URL`,
`SUPPORT_PROMPT_LAB_SAMPLE_3_URL`, and `SUPPORT_PROMPT_LAB_SAMPLE_5_URL`. This live
comparison makes multiple model calls and can incur API charges.

The comparison command also generates JSON and Markdown summaries with policy and
escalation accuracy, consensus rates, average and p95 latency, total workflow tokens,
and estimated cost. Pricing is configured by exact model name in
`evaluations/pricing/model-pricing.json`; update or add an entry whenever the runtime
model or its rates change. Cost estimates treat all reported input tokens as uncached.
