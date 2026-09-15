# AGENTS.md — ChronoLog Orchestrator (opencode)

> Single root orchestrator. Keep under 80 lines. Details live in `skill()` / `doc/`. Do not preload everything.

## Orchestrator role
Root dispatcher. On each prompt: check `git status --short`, `doc/tasks-v6.md`, active files; route to one subagent + one skill; run non-interactive commands only (`pytest -q`, `docker compose up -d`). Parallelize independent work with `Task` + `Todowrite`.

## Stack & layout
Python 3.12 + Gradio + SQLAlchemy/psycopg2 + PostgreSQL + Docker Compose. Python only in `src/`.
`src/modules/{auth,clients,appointments}/{domain,use-cases,infrastructure}/` + `src/core/shared/` + `tests/` mirror. `doc/` is docs source of truth.

## Hard rules
1. DIP: `domain/` is pure, zero imports from `sqlalchemy|gradio|fastapi|infrastructure`. Use-cases depend only on ports `IClientRepository`, `IAppointmentRepository`.
2. AuthZ: every query/mutation scoped by `user_id` (`findByIdAndUserId`). No `user_id`, no query.
3. Secrets only in `.env` (git-ignored). Never in code/logs.
4. SDD + TDD RED-GREEN-REFACTOR mandatory in `domain/` + `use-cases/` (TSK-005..011). MoSCoW MUST bounds enforced, no scope creep.
5. Commits: `feat(domain): ... (closes TSK-XXX)`. Update `doc/tasks-v6.md`, never delete history.

## Lazy-load (Read only on trigger)
- Scope/MoSCoW: `doc/proposal.md`
- Architecture: `doc/adr-001-architectural-style.md`
- Backlog: `doc/tasks-v6.md`
- Tooling SDD/TDD: `doc/information.md`

## Router -> agents + skills
| Trigger | Invoke | Skill |
|---|---|---|
| Scope, PRD, MoSCoW | `@po-analyst` | `skill({name:"sdd-spec"})` |
| Domain, entities, use-cases TSK-005..011 | `@backend-dev` | `skill({name:"sdd-apply"})` |
| Gradio forms, wiring TSK-016..017 | `@frontend-dev` | `skill({name:"ui-integration"})` |
| Tests, coverage >=85% TSK-018 | `@qa-tester` | `skill({name:"sdd-verify"})` |
| IDOR, injection, `user_id` TSK-015 | `@security-auditor` | `skill({name:"security-audit"})` |
| Dockerfile, compose, `.env` TSK-012..014 | `@devops-engineer` | `skill({name:"devops-docker"})` |

## Commands
- Test: `pytest tests/ -q --cov=src --cov-fail-under=85`
- Lint/types: `ruff check src tests` + `mypy src`
- Scan: `bandit -r src -q`
- Docker: `docker compose up --build -d` / `docker compose down`
- Shortcuts: `/apply TSK-XXX`, `/verify`, `/sec`, `/up`

## Response format (concise)
Target: `TSK-XXX` / Actions: files + commands / Verification: tests-lint-scan / Next step.

## DoD (before `[x]` in tasks-v6.md)
- [ ] `pytest` green + cov >=85% on domain/use-cases
- [ ] `ruff` + `mypy` clean, `bandit` no criticals
- [ ] AuthZ `user_id` covered by test, no secrets
- [ ] `docker compose up --build -d` ok + ADR if major change
