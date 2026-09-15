---
description: Verify DoD + coverage
agent: qa-tester
---

Run in order: 1) pytest tests/ -q --cov=src --cov-fail-under=85 2) grep -rE "sqlalchemy|gradio|fastapi" src/modules/*/domain (0 matches) 3) ruff check src tests + mypy src 4) bandit -r src -q 5) docker compose up --build -d + docker compose ps. Block done on failure. Report in doc/tasks.md.
