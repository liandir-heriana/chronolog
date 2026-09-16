# ChronoLog Task Backlog & Tracking (tasks.md)

This document is the **single source of truth** for tracking the progress, lifecycle, and history of all tasks in the **ChronoLog** Appointment & Session Management MVP project. It is governed by the root orchestrator `/AGENTS.md` (opencode). It follows GTD and Spec-Driven Development (SDD): spec -> tasks -> apply (TDD) -> verify -> archive, recording exact dates for each transition to prevent technical debt.

## Sprint Dashboard Overview

*   **Project Phase**: Phase 1: Planning & Setup
*   **Total Tasks**: 20
*   **Pending (Proposed)**: 7
*   **In Progress**: 0
*   **Completed**: 13
*   **Current Progress**: 65.00% [██████░░░░]

---

## Complete Task Backlog

### Phase 1: Planning & Setup
*Status: In Progress*

#### [x] TSK-000: Project Naming and Brand Identity Definition (ChronoLog)
*   **Description**: Brainstorm, select, and establish a meaningful name and professional brand identity for the MVP project that aligns with Clean Architecture and generalist appointment/session logging.
*   **Proposed**: 2026-09-07 12:00 (UTC)
*   **Started**: 2026-09-07 12:01 (UTC)
*   **Completed**: 2026-09-07 12:08 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Notes**: Selected 'ChronoLog' as official name, establishing a generalist professional appointment and session logging platform brand.

#### [x] TSK-001: Draft Formal Project Proposal (proposal.md)
*   **Description**: Define context, business problems, detailed MoSCoW MVP scope (including Docker containerization & AuthN/AuthZ requirements), architecture directory layouts, and quality gates for ChronoLog.
*   **Proposed**: 2026-09-07 11:45 (UTC)
*   **Started**: 2026-09-07 11:46 (UTC)
*   **Completed**: 2026-09-15 02:50 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Notes**: Updated and published to `doc/proposal.md` in English, incorporating Docker local containerization and user data isolation / AuthN & AuthZ requirements.

#### [x] TSK-002: Establish Architectural Style Decision (adr-001-architectural-style.md)
*   **Description**: Redact the initial Architecture Decision Record (`doc/adr-001-architectural-style.md`) outlining reasons, context, alternatives, and consequences of choosing a Modular Monolith with Clean/Hexagonal Architecture for ChronoLog.
*   **Proposed**: 2026-09-07 11:45 (UTC)
*   **Started**: 2026-09-07 11:46 (UTC)
*   **Completed**: 2026-09-07 11:56 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Notes**: Updated and published as `doc/adr-001-architectural-style.md`.

#### [x] TSK-003: Compile English Reference Guide (information.md)
*   **Description**: Create a complete technical and project reference summary in English compiling core architectural philosophies, SDD/TDD steps, and AI-assisted development tools (v0, Lovable, Gradio) for ChronoLog.
*   **Proposed**: 2026-09-07 11:40 (UTC)
*   **Started**: 2026-09-07 11:41 (UTC)
*   **Completed**: 2026-09-07 11:46 (UTC)
*   **Assignee**: Developer (Human) + AI Copilot
*   **Notes**: Updated and published as `doc/information.md`.

#### [x] TSK-004: Consolidate Single Root Orchestrator (AGENTS.md for opencode)
*   **Description**: Consolidate `doc/AGENTS.md` and `AGENTS (1).md` into a single English root `/AGENTS.md` (<80 lines) for opencode. Define stack, layout, DIP/AuthZ rules, lazy-load sources, actionable router to subagents + skills, non-interactive commands, and DoD. Backed by `.opencode/agents/`, `.opencode/skills/*/SKILL.md`, `.opencode/commands/`, and `opencode.json` instructions.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-15 03:20 (UTC)
*   **Completed**: 2026-09-15 12:00 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Route**: Root orchestrator, no skill
*   **Notes**: Removed duplicate `AGENTS (1).md`. Single `/AGENTS.md` kept. `opencode.json` points to `doc/proposal.md`, `doc/adr-001-architectural-style.md`, `doc/tasks.md`, `doc/information.md`.

---

### Phase 2: Core Domain & Entities (Pure Python)
*Status: In Progress*

#### [x] TSK-005: Model Client Aggregate Root & Value Objects
*   **Description**: Implement pure Python classes for the `Client` Entity and corresponding Value Objects (Email, Phone, ID) containing strict, self-contained business validations.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-15 14:11 (UTC)
*   **Completed**: 2026-09-15 14:14 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-005`
*   **Notes**: RED test first (26 tests, failed on collection), GREEN pure domain `src/modules/clients/domain/` (entities, value_objects, exceptions, stdlib only). Verify: pytest 26 passed, cov 100%, ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (no infra in domain task, deferred to TSK-012). Fixed boundary glob to `src/modules/*/domain` in AGENTS/skill/verify.

#### [x] TSK-006: Model Appointment & SessionNotes Core Domains
*   **Description**: Implement the `Appointment` and `SessionNotes` pure entities. Define domain business rules (e.g., appointments cannot be scheduled in the past, session notes are only editable once an appointment is completed).
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-15 14:50 (UTC)
*   **Completed**: 2026-09-15 14:51 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-006`
*   **Notes**: RED test first (14 tests, failed on collection), GREEN pure domain `src/modules/appointments/domain/` (entities, value_objects, exceptions, stdlib only). Rules: explicit `now` in `schedule()` for testability, tz-aware datetimes, SCHEDULED->COMPLETED/CANCELLED transitions, notes attach/edit only when COMPLETED and bound to same appointment. Verify: pytest 40 passed, cov 97.38%, ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (deferred to TSK-012).

#### [x] TSK-007: Define Domain Repository Ports (Interfaces)
*   **Description**: Design abstract classes (ports) `IClientRepository` and `IAppointmentRepository` in the domain layer, isolating core business domain code from database dependencies.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-16 10:44 (UTC)
*   **Completed**: 2026-09-16 10:45 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-007`
*   **Notes**: RED test first (11 tests, failed on collection with ModuleNotFoundError), GREEN pure domain ports `src/modules/clients/domain/repository_interfaces.py` (IClientRepository: save/find_by_id_and_user_id/list_by_user_id) + `src/modules/appointments/domain/repository_interfaces.py` (IAppointmentRepository: save/find_by_id_and_user_id/list_by_user_id/list_by_client_and_user_id/list_overlapping), exported from domain `__init__.py`, stdlib+domain only. Every read scoped by user_id (IDOR prevention), overlap lookup supports exclude_appointment_id. Verify: pytest 51 passed, cov 94.30%, ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (pure domain, deferred to TSK-012/014).

---

### Phase 3: Application Use Cases & Auth Logic (TDD Backend Logic)
*Status: In Progress*

#### [x] TSK-008: Implement 'User Authentication & Registration' Use Case
*   **Description**: Implement user account registration, password hashing (bcrypt/Argon2), and login token generation use cases.
*   **Proposed**: 2026-09-15 02:50 (UTC)
*   **Started**: 2026-09-16 10:56 (UTC)
*   **Completed**: 2026-09-16 10:58 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-008`
*   **Notes**: RED test first (38 cases, failed collection with ModuleNotFoundError), GREEN pure `src/modules/auth/domain/` (User, AuthSession, UserEmail/UserId, IUserRepository, PBKDF2 security, stdlib only) + `src/modules/auth/use_cases/` (RegisterUser, AuthenticateUser, ports only). Hashing: PBKDF2-HMAC-SHA256/210k iters/16-B salt (bcrypt/argon2 not installed, zero native deps); token: opaque secrets.token_urlsafe (no JWT); generic InvalidCredentialsError on all login failures (no enumeration). Verify: pytest 89 passed, cov 94.84%, ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (deferred to TSK-012/014). Guide: `verify/task8_test.md`.

#### [x] TSK-009: Implement 'Schedule Appointment' Use Case with User Data Isolation
*   **Description**: Write application use case `ScheduleAppointment`. Implement TDD verification tests ensuring scheduling logic runs correctly, respects `user_id` ownership, and raises a domain error on schedule overlaps.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-16 11:17 (UTC)
*   **Completed**: 2026-09-16 11:18 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-009`
*   **Review from TSK-006/007**: appointments use the `starts_at/ends_at` window model (D1) — detect overlaps via `IAppointmentRepository.list_overlapping(user_id, starts_at, ends_at, exclude_appointment_id)` (T7-D3), not `date_time + duration_minutes`.
*   **Notes**: RED test first (9 tests, failed collection with ModuleNotFoundError), GREEN pure `src/modules/appointments/use_cases/` (ScheduleAppointment(repo, clients).execute(*, user_id, client_id, starts_at, ends_at, now) -> Appointment, stdlib+domain only). AuthZ: client ownership via IClientRepository.find_by_id_and_user_id (unknown/foreign -> AppointmentValidationError, no oracle/IDOR); window via Appointment.schedule (past/ends<=starts/naive rejected); overlap via list_overlapping half-open [S,E) (same-user overlap rejected, adjacent allowed, other-user invisible) with unified AppointmentValidationError (T9-D1, no granular errors). Verify: pytest 98 passed (89+9), cov 95.14% (use-case 100%), ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (deferred to TSK-012/014). Guide: `verify/task9_test.md`.

#### [x] TSK-010: Implement 'Complete Appointment & Add Session Notes' Use Case
*   **Description**: Write application use case `CompleteAppointment` which receives the text-based session notes and links them securely to the correct historical appointment for the authorized `user_id`.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-16 11:30 (UTC)
*   **Completed**: 2026-09-16 11:32 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-010`
*   **Review from TSK-006/007**: notes are created via the `Appointment.attach_notes()` factory and persist with the aggregate (D4); decide here whether separate notes persistence (`save_session_notes` / `find_notes_by_*`, T7-D5) is needed.
*   **Notes**: RED test first (10 tests, failed collection with ModuleNotFoundError), GREEN pure `src/modules/appointments/use_cases/complete_appointment.py` (CompleteAppointment(repo).execute(*, appointment_id, user_id, content) -> Appointment, stdlib+domain only). AuthZ: find_by_id_and_user_id (unknown/foreign -> same AppointmentValidationError, no oracle); lifecycle via complete() (already-completed/cancelled rejected); notes via attach_notes (empty/blank/overlong rejected, bound to same appointment/user); aggregate save, no new port methods (T10-D1). Verify: pytest 108 passed (98+10), cov 95.34% (use-case 100%), ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (deferred to TSK-012/014). Guide: `verify/task10_test.md`.

#### [x] TSK-011: Implement 'Get Client Interaction History' Use Case
*   **Description**: Write application use case `GetClientHistory` to compile and return a client profile along with all their past chronological appointments and manual session notes owned by the authenticated `user_id`.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: 2026-09-16 11:46 (UTC)
*   **Completed**: 2026-09-16 11:48 (UTC)
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-011`
*   **Notes**: RED test first (6 tests, failed collection with ModuleNotFoundError), GREEN pure `src/modules/appointments/use_cases/get_client_history.py` (GetClientHistory(clients, appointments).execute(*, user_id, client_id) -> ClientHistory frozen read model (client + appointments tuple sorted ascending starts_at), stdlib+domain only). AuthZ: clients.find_by_id_and_user_id (unknown/foreign -> same AppointmentValidationError, no oracle); history via list_by_client_and_user_id on normalized client.id.value scoped by user_id (other-user never leaks, zero -> empty tuple not error, unsorted seed sorted); notes travel via aggregate attach_notes (no separate lookup, T10-D1); no DTO layer (T9-D2, T11-D1). Verify: pytest 114 passed (108+6), cov 95.61% (use-case 100%), ruff/mypy/bandit clean, boundary grep 0 matches. Docker N/A (deferred to TSK-012/014). Guide: `verify/task11_test.md`.

---

### Phase 4: Infrastructure, Persistence & Containerization
*Status: Pending*

#### [x] TSK-012: Local Docker Containerization Setup (Dockerfile & docker-compose.yml)
*   **Description**: Create production-ready `Dockerfile` and `docker-compose.yml` orchestrating backend app and PostgreSQL database containers with local environment volume persistence.
*   **Proposed**: 2026-09-15 02:50 (UTC)
*   **Started**: 2026-09-16 11:58 (UTC)
*   **Completed**: 2026-09-16 11:59 (UTC)
*   **Assignee**: @devops-engineer
*   **Route**: `skill({name:"devops-docker"})` via `/up`
*   **Notes**: Artifacts: `Dockerfile` (python:3.12-slim, non-root appuser, honest CMD runs pytest suite — no Gradio server invented), `docker-compose.yml` (app + postgres:16, named volume chronolog-pgdata, pg_isready healthcheck, app depends_on healthy postgres, ${...:-} defaults so `config` validates without `.env`), `.env.example` (POSTGRES_USER/PASSWORD/DB placeholders, `changeme` only). Verified: pytest 114 passed (no .py changed, baseline held), compose YAML structure asserted via PyYAML (services/healthcheck/volume/depends_on), `.env` git-ignored (`git check-ignore` ok, no `.env` tracked/committed), `.env.example` holds placeholders only. BLOCKED-ON-ENV: `docker` binary absent (`which docker` empty) so `docker compose config` / `up --build` could NOT run — static verification at 75% (see `verify/task12_test.md` §6), live gate pending TSK-012.1. Service wiring (app actually connecting to postgres) belongs to TSK-014; server ports belong to TSK-016. Guide: `verify/task12_test.md`.

#### [ ] TSK-012.1: Provision Docker Engine & Run Live Healthcheck Gate
*   **Description**: On a Docker-capable host: `cp .env.example .env`, then `docker compose config`, `docker compose up --build -d`, `docker compose ps` (both services running), `pg_isready` exit 0, `docker compose down`. Clears the TSK-012 BLOCKED-ON-ENV live gate. Must complete before TSK-013/TSK-014 live validation.
*   **Proposed**: 2026-09-16 12:00 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @devops-engineer
*   **Route**: `skill({name:"devops-docker"})` via `/up`

#### [ ] TSK-013: SQL Database Schema Design & Migration Scripts
*   **Description**: Define relational SQL schema tables (`users`, `clients`, `appointments`, `session_notes`) using proper foreign keys, `user_id` indexes, and prepare migration scripts.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @devops-engineer
*   **Route**: `skill({name:"devops-docker"})`

#### [ ] TSK-014: Implement Postgres Database Repositories (Adapters)
*   **Description**: Write concrete repository implementations (adapters) that fulfill `IClientRepository` and `IAppointmentRepository` interfaces with user-level isolation using SQLAlchemy or psycopg2.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` + `skill({name:"security-audit"})`
*   **Review from TSK-007**: `delete_by_id_and_user_id` was deferred (T7-D4, no delete in MUST) — add it with its own RED cycle only if a use-case requires it; keep the unified `AppointmentValidationError`/`ClientValidationError` unless the audit mandates granular exceptions (D3).

#### [ ] TSK-015: Configure Server-Side AuthN/AuthZ Middleware & Security Scans
*   **Description**: Implement HTTP authentication/authorization middleware verifying JWT/session tokens on every route, ensuring IDOR prevention and configuring SAST scanners (Bandit).
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @security-auditor
*   **Route**: `skill({name:"security-audit"})` via `/sec`
*   **Review from TSK-008**: auth uses PBKDF2-HMAC-SHA256/210k + opaque `secrets` tokens (stdlib, zero native deps; see `src/modules/auth/domain/security.py`). Decide here whether to mandate argon2id, add login rate-limiting, session expiry/revocation, and confirm the versioned hash format migration path.

---

### Phase 5: Presentation & UI Layer (Web MVP)
*Status: Pending*

#### [ ] TSK-016: Set Up Web UI Interface & Login Screen (Gradio)
*   **Description**: Implement Gradio dashboard boilerplate with Login/Register forms and layout tabs for Client Registration, Scheduler, and Session Notes Review.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @frontend-dev
*   **Route**: `skill({name:"ui-integration"})`

#### [ ] TSK-017: Connect UI Forms to Application Use Cases
*   **Description**: Wire Gradio inputs (text fields, date pickers, dropdowns) directly into Hexagonal Core backend Use Cases with authenticated user context.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @frontend-dev
*   **Route**: `skill({name:"ui-integration"})`

---

### Phase 6: Quality Verification & Project Delivery
*Status: Pending*

#### [ ] TSK-018: Execute Final Test Suite & Generate Coverage Report
*   **Description**: Run automated unit, integration, and security tests in Docker environment. Ensure code coverage is at or above the strict 85% requirement defined in DoD.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @qa-tester
*   **Route**: `skill({name:"sdd-verify"})` via `/verify`

---

## Lifecycle Instructions for Devs and AI Agents

To update tasks in this file, follow these precise instructions:
1.  **Do not delete history**: Keep all completed and pending tasks to maintain a full audit trail.
2.  **SDD is mandatory**: Follow explore -> propose -> spec <-> design -> tasks -> apply (TDD RED-GREEN-REFACTOR) -> verify -> archive on every task. No improvisation.
3.  **Use the orchestrator**: Root `/AGENTS.md` routes every task via `Task` to one subagent in `.opencode/agents/` plus one `skill()`. Run non-interactive commands only. Parallelize independent tasks with `Task` + `Todowrite`.
4.  **State progression**:
    *   When beginning a task: Change status to `[/] In Progress`, add current timestamp to `Started` and update **Sprint Dashboard** counts.
    *   When completing a task: Meet the DoD in `/AGENTS.md` (`pytest` + cov >=85%, `ruff` + `mypy` clean, `bandit` no criticals, boundary grep 0 matches, AuthZ `user_id` tested, `docker compose up --build -d` ok, use `/verify` and `/sec`), then run `/archive`, change status to `[x] Completed`, add current timestamp to `Completed`, update counts, and note down brief artifacts/outcomes in `Notes` section.
5.  **Ensure Traceability**: Always mention corresponding task IDs (`TSK-XXX`) in Git commit messages (e.g., `git commit -m "feat(domain): implement Client value objects (closes TSK-005)"`).
