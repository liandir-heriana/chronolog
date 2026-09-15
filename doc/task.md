# ChronoLog Task Backlog & Tracking (tasks-v6.md)

This document is the **single source of truth** for tracking the progress, lifecycle, and history of all tasks in the **ChronoLog** Appointment & Session Management MVP project. It is governed by the root orchestrator `/AGENTS.md` (opencode). It follows GTD and Spec-Driven Development (SDD): spec -> tasks -> apply (TDD) -> verify -> archive, recording exact dates for each transition to prevent technical debt.

## Sprint Dashboard Overview

*   **Project Phase**: Phase 1: Planning & Setup
*   **Total Tasks**: 19
*   **Pending (Proposed)**: 14
*   **In Progress**: 0
*   **Completed**: 5
*   **Current Progress**: 26.32% [██░░░░░░░░]

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
*   **Notes**: Removed duplicate `AGENTS (1).md`. Single `/AGENTS.md` kept. `opencode.json` points to `doc/proposal.md`, `doc/adr-001-architectural-style.md`, `doc/tasks-v6.md`, `doc/information.md`.

#### [ ] TSK-005: Model Client Aggregate Root & Value Objects
*   **Description**: Implement pure Python classes for the `Client` Entity and corresponding Value Objects (Email, Phone, ID) containing strict, self-contained business validations.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-005`

#### [ ] TSK-006: Model Appointment & SessionNotes Core Domains
*   **Description**: Implement the `Appointment` and `SessionNotes` pure entities. Define domain business rules (e.g., appointments cannot be scheduled in the past, session notes are only editable once an appointment is completed).
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-006`

#### [ ] TSK-007: Define Domain Repository Ports (Interfaces)
*   **Description**: Design abstract classes (ports) `IClientRepository` and `IAppointmentRepository` in the domain layer, isolating core business domain code from database dependencies.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-007`

---

### Phase 3: Application Use Cases & Auth Logic (TDD Backend Logic)
*Status: Pending*

#### [ ] TSK-008: Implement 'User Authentication & Registration' Use Case
*   **Description**: Implement user account registration, password hashing (bcrypt/Argon2), and login token generation use cases.
*   **Proposed**: 2026-09-15 02:50 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-008`

#### [ ] TSK-009: Implement 'Schedule Appointment' Use Case with User Data Isolation
*   **Description**: Write application use case `ScheduleAppointment`. Implement TDD verification tests ensuring scheduling logic runs correctly, respects `user_id` ownership, and raises a domain error on schedule overlaps.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-009`

#### [ ] TSK-010: Implement 'Complete Appointment & Add Session Notes' Use Case
*   **Description**: Write application use case `CompleteAppointment` which receives the text-based session notes and links them securely to the correct historical appointment for the authorized `user_id`.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-010`

#### [ ] TSK-011: Implement 'Get Client Interaction History' Use Case
*   **Description**: Write application use case `GetClientHistory` to compile and return a client profile along with all their past chronological appointments and manual session notes owned by the authenticated `user_id`.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @backend-dev
*   **Route**: `skill({name:"sdd-apply"})` via `/apply TSK-011`

---

### Phase 4: Infrastructure, Persistence & Containerization
*Status: Pending*

#### [ ] TSK-012: Local Docker Containerization Setup (Dockerfile & docker-compose.yml)
*   **Description**: Create production-ready `Dockerfile` and `docker-compose.yml` orchestrating backend app and PostgreSQL database containers with local environment volume persistence.
*   **Proposed**: 2026-09-15 02:50 (UTC)
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

#### [ ] TSK-015: Configure Server-Side AuthN/AuthZ Middleware & Security Scans
*   **Description**: Implement HTTP authentication/authorization middleware verifying JWT/session tokens on every route, ensuring IDOR prevention and configuring SAST scanners (Bandit).
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: @security-auditor
*   **Route**: `skill({name:"security-audit"})` via `/sec`

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
2.  **Use the orchestrator**: Root `/AGENTS.md` routes every task via `Task` to one subagent in `.opencode/agents/` plus one `skill()`. Run non-interactive commands only. Parallelize independent tasks with `Task` + `Todowrite`.
3.  **State progression**:
    *   When beginning a task: Change status to `[/] In Progress`, add current timestamp to `Started` and update **Sprint Dashboard** counts.
    *   When completing a task: Meet the DoD in `/AGENTS.md` (`pytest` + cov >=85%, `ruff` + `mypy` clean, `bandit` no criticals, AuthZ `user_id` tested, `docker compose up --build -d` ok, use `/verify` and `/sec`), change status to `[x] Completed`, add current timestamp to `Completed`, update counts, and note down brief artifacts/outcomes in `Notes` section.
4.  **Ensure Traceability**: Always mention corresponding task IDs (`TSK-XXX`) in Git commit messages (e.g., `git commit -m "feat(domain): implement Client value objects (closes TSK-005)"`).
