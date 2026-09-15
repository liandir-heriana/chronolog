---
description: Verify DoD + coverage
agent: qa-tester
---

Run pytest --cov=src --cov-fail-under=85, ruff, mypy, bandit. Block done on failure. Report in doc/tasks-v6.md.
