# ChronoLog backend image — Python 3.12 (matches AGENTS.md stack).
# NOTE (TSK-012): no Gradio app entrypoint exists yet (UI lands in TSK-016,
# postgres adapters in TSK-014), so the honest default CMD runs the test
# suite instead of inventing an app server. The CMD will be replaced with
# the Gradio launch command once `src/` gains a composition root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime deps: psycopg2-binary for TSK-014 Postgres adapters (wheels bundle
# libpq, no system build deps); no sqlalchemy — raw parameterized SQL keeps
# the adapters thin and auditable (see verify/task14_test.md decision table).
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir pytest pytest-cov psycopg2-binary

COPY src/ ./src/
COPY tests/ ./tests/

# Run as non-root for production readiness.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

# Honest default: verify the image by running the suite.
# Overridable at runtime, e.g. `docker compose run app python -m pytest tests/ -q`.
CMD ["python", "-m", "pytest", "tests/", "-q"]
