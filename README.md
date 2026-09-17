# ChronoLog

ChronoLog is a modular monolith platform for appointment scheduling and session logging, built with Clean Architecture (Hexagonal). Final target: a web app launched with Docker.

## Stack

- Python 3.12 domain and use-cases, Gradio web UI, SQLAlchemy/psycopg2, PostgreSQL
- Docker Compose: `app` (Gradio/Python web server) + `postgres` (from TSK-012 on)
- Quality gates: `pytest` + coverage, `ruff`, `mypy`, `bandit`, domain boundary `grep`

## Requirements

- Python 3.12+ (`python3 --version`)
- A virtual environment (the repo has no system-wide deps; everything runs from `.venv`)
- Docker + Docker Compose (only needed from Phase 4 infrastructure tasks on)

## Setup (local, no Docker needed for domain tasks)

```bash
# 1. Create an isolated env (add --without-pip only if your distro ships python without pip, e.g. PEP 668 systems)
python3 -m venv .venv
.venv/bin/python -m pip install -q pytest pytest-cov ruff mypy bandit

# 2. Sanity check
.venv/bin/python -m pytest tests/ -q
```

Notes:

- `.venv/` is git-ignored (see `.gitignore`). Never commit it.
- If `python3 -m venv` cannot bootstrap pip on your distro, create with `python3 -m venv --without-pip .venv` and install pip inside it from the official bootstrap (`get-pip.py` with `.venv/bin/python`), then install the packages above.
- Python 3.14 also works; `pyproject.toml` targets `py312` syntax as the baseline.

## Run the gates (Definition of Done)

```bash
.venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85
grep -rE "sqlalchemy|gradio|fastapi" src/modules/*/domain   # must return 0 matches
.venv/bin/ruff check src tests
.venv/bin/mypy src
.venv/bin/bandit -r src -q
```

Live postgres integration tests need a reachable DB. Compose publishes
postgres on loopback (`127.0.0.1:5432`, LAN-invisible), so the default
`localhost` just works:

```bash
docker compose up -d postgres && sleep 5
.venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85
docker compose down   # without -v, keeps the volume
```

(Fallback: tests also honor `PGHOST`/`PGPORT` if you point them at another server.)

Shortcuts when working in opencode: `/apply TSK-XXX`, `/verify`, `/sec`, `/up`, `/archive`.

## Run the stack (Docker)

```bash
cp .env.example .env   # adjust values; .env is git-ignored, never commit it
docker compose config  # sanity check interpolation
docker compose up --build -d
docker compose ps      # postgres must be Healthy
docker compose down    # stop; add -v only to wipe the database volume
```

Notes:

- The `app` container serves the Gradio dashboard on `:7860` (composition
  root `src/main.py` ensures `V001+V002+V003` then launches
  `0.0.0.0:7860`; compose publishes it on loopback `127.0.0.1:7860`,
  LAN-invisible like postgres). Open `http://localhost:7860`, register,
  log in, then use the Clients / Scheduler / History tabs.
- A Healthy `postgres` plus `* Running on local URL: http://0.0.0.0:7860`
  in the app logs is the expected green state (`curl localhost:7860` → 200).
- If `docker` denies access to the daemon, the durable fix is
  `sudo usermod -aG docker $USER` followed by a re-login.

## Project layout

```text
src/modules/{auth,clients,appointments}/{domain,use-cases,infrastructure}/
src/core/shared/
tests/            # mirrors src/
db/migrations/    # versioned SQL (V001, V002...), apply order in db/README.md
doc/              # source of truth: proposal.md, adr-001-*, tasks.md, information.md
.opencode/        # agents, skills, commands for opencode
```

Rules: `domain/` is pure (no `sqlalchemy|gradio|fastapi` imports), every query is scoped by `user_id`, secrets live only in `.env`.

## Workflow

Mandatory SDD + Strict TDD, no vibe coding: spec first, `/apply` writes the failing test before production code, every task passes `/verify` and `/archive`. See `/AGENTS.md` (orchestrator) and `doc/tasks.md` (backlog).
