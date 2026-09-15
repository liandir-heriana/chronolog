---
name: sdd-verify
description: Verify ChronoLog DoD with robust Python-realizable gates. Use for TSK-018 and task closure.
---

## What I do
1. Unit/integration (local, fast): `pytest tests/ -q --cov=src --cov-fail-under=85`.
2. Static boundary: `grep -rE "sqlalchemy|gradio|fastapi" src/*/domain` must return 0 matches.
3. Lint/types realizable: `ruff check src tests`, `mypy src`.
4. Security realizable: `bandit -r src -q` (no criticals).
5. Docker web target: `docker compose up --build -d`, then `docker compose ps`.
- Block [x] if any gate fails. Record output in task Notes.

## When to use me
Before marking done in tasks.md, and before archive.
