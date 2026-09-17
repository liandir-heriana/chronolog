# ChronoLog backend image — Python 3.12 (matches AGENTS.md stack).
# TSK-016: composition root exists (`src/main.py`), so the CMD serves the
# Gradio dashboard on 0.0.0.0:7860 (compose publishes it on loopback).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime deps: psycopg2-binary for Postgres adapters (wheels bundle libpq,
# no system build deps) + gradio for the presentation layer (TSK-016).
# No sqlalchemy — raw parameterized SQL keeps the adapters thin and
# auditable (see verify/task14_test.md decision table).
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir pytest pytest-cov psycopg2-binary gradio

COPY src/ ./src/
COPY tests/ ./tests/
COPY db/ ./db/

# Run as non-root for production readiness.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

# Serve the Gradio dashboard (composition root ensures V001+V002+V003 first).
# Overridable at runtime, e.g. `docker compose run app python -m pytest tests/ -q`.
CMD ["python", "-m", "src.main"]
