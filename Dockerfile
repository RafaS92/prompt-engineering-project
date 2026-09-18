# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.16 AS uv

FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY README.md pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /app/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "support_prompt_lab.main:app", "--host", "0.0.0.0", "--port", "8000"]

