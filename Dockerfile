# ChronoLog backend image — Python 3.12 (matches AGENTS.md stack).
# NOTE (TSK-012): no Gradio app entrypoint exists yet (UI lands in TSK-016,
# postgres adapters in TSK-014), so the honest default CMD runs the test
# suite instead of inventing an app server. The CMD will be replaced with
# the Gradio launch command once `src/` gains a composition root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Test tooling only: src/ itself is stdlib-only (no runtime deps yet).
# Runtime deps (sqlalchemy/psycopg2/gradio) get installed here in TSK-014/016.
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir pytest pytest-cov

COPY src/ ./src/
COPY tests/ ./tests/

# Run as non-root for production readiness.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

# Honest default: verify the image by running the suite.
# Overridable at runtime, e.g. `docker compose run app python -m pytest tests/ -q`.
CMD ["python", "-m", "pytest", "tests/", "-q"]
