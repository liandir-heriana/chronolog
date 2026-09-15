# ChronoLog Task Backlog & Tracking (tasks.md)

This document is the **single source of truth** for tracking the progress, lifecycle, and history of all tasks in the **ChronoLog** Appointment & Session Management MVP project. It follows a rigorous GTD (Getting Things Done) [1] and Spec-Driven Development (SDD) [55] methodology, recording exact dates and times for each lifecycle transition to prevent technical debt and maintain process visibility.

## 📊 Sprint Dashboard Overview

*   **Project Phase**: Phase 1: Planning & Setup
*   **Total Tasks**: 19
*   **Pending (Proposed)**: 15
*   **In Progress**: 0
*   **Completed**: 4
*   **Current Progress**: 21.05% [██░░░░░░░░]

---

## 🛠️ Complete Task Backlog

### Phase 1: Planning & Setup
*Status: In Progress*

#### [x] TSK-000: Project Naming and Brand Identity Definition (ChronoLog)
*   **Description**: Brainstorm, select, and establish a meaningful name and professional brand identity for the MVP project that aligns with Clean Architecture and generalist appointment/session logging.
*   **Proposed**: 2026-09-07 12:00 (UTC)
*   **Started**: 2026-09-07 12:01 (UTC)
*   **Completed**: 2026-09-07 12:08 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Notes**: Selected 'ChronoLog' as official name, establishing a generalist professional appointment and session logging platform brand.

#### [x] TSK-001: Draft Formal Project Proposal (proposal-v4.md)
*   **Description**: Define context, business problems, detailed MoSCoW MVP scope (including Docker containerization & AuthN/AuthZ requirements), architecture directory layouts, and quality gates for ChronoLog.
*   **Proposed**: 2026-09-07 11:45 (UTC)
*   **Started**: 2026-09-07 11:46 (UTC)
*   **Completed**: 2026-09-15 02:50 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Notes**: Updated and published to `proposal-v4.md` in English, incorporating Docker local containerization and user data isolation / AuthN & AuthZ requirements.

#### [x] TSK-002: Establish Architectural Style Decision (adr-001-architectural-style-v2)
*   **Description**: Redact the initial Architecture Decision Record (`adr-001-architectural-style-v2.md`) outlining reasons, context, alternatives, and consequences of choosing a Modular Monolith with Clean/Hexagonal Architecture for ChronoLog.
*   **Proposed**: 2026-09-07 11:45 (UTC)
*   **Started**: 2026-09-07 11:46 (UTC)
*   **Completed**: 2026-09-07 11:56 (UTC)
*   **Assignee**: Architect (Human) + Orchestrator (AI)
*   **Notes**: Updated and published as `adr-001-architectural-style-v2.md`.

#### [x] TSK-003: Compile English Reference Guide (information-v2.md)
*   **Description**: Create a complete technical and project reference summary in English compiling core architectural philosophies, SDD/TDD steps, and AI-assisted development tools (v0, Lovable, Gradio) for ChronoLog.
*   **Proposed**: 2026-09-07 11:40 (UTC)
*   **Started**: 2026-09-07 11:41 (UTC)
*   **Completed**: 2026-09-07 11:46 (UTC)
*   **Assignee**: Developer (Human) + AI Copilot
*   **Notes**: Updated and published as `information-v2.md`.

#### [ ] TSK-004: Create AI Sovereignty Guardrails (AGENTS.md)
*   **Description**: Draft the `AGENTS.md` system context rules for the root of the IDE workspace. This serves as the source of truth instructions for local coding models (Cursor/VS Code) to ensure they respect the hexagonal boundary rules in ChronoLog.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: Architect (Human)

---

### Phase 2: Core Domain & Entities (Pure Python)
*Status: Pending*

#### [ ] TSK-005: Model Client Aggregate Root & Value Objects
*   **Description**: Implement pure Python classes for the `Client` Entity and corresponding Value Objects (Email, Phone, ID) containing strict, self-contained business validations.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer (Under TDD Cycle)

#### [ ] TSK-006: Model Appointment & SessionNotes Core Domains
*   **Description**: Implement the `Appointment` and `SessionNotes` pure entities. Define domain business rules (e.g., appointments cannot be scheduled in the past, session notes are only editable once an appointment is completed).
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer (Under TDD Cycle)

#### [ ] TSK-007: Define Domain Repository Ports (Interfaces)
*   **Description**: Design abstract classes (ports) `IClientRepository` and `IAppointmentRepository` in the domain layer, isolating core business domain code from database dependencies [86].
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: Lead Developer

---

### Phase 3: Application Use Cases & Auth Logic (TDD Backend Logic)
*Status: Pending*

#### [ ] TSK-008: Implement 'User Authentication & Registration' Use Case
*   **Description**: Implement user account registration, password hashing (bcrypt/Argon2), and login token generation use cases [22, 53].
*   **Proposed**: 2026-09-15 02:50 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer (Under TDD Cycle)

#### [ ] TSK-009: Implement 'Schedule Appointment' Use Case with User Data Isolation
*   **Description**: Write application use case `ScheduleAppointment`. Implement TDD verification tests ensuring scheduling logic runs correctly, respects `userId` ownership, and raises a domain error on schedule overlaps.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer (Under TDD Cycle)

#### [ ] TSK-010: Implement 'Complete Appointment & Add Session Notes' Use Case
*   **Description**: Write application use case `CompleteAppointment` which receives the text-based session notes and links them securely to the correct historical appointment for the authorized `userId`.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer (Under TDD Cycle)

#### [ ] TSK-011: Implement 'Get Client Interaction History' Use Case
*   **Description**: Write application use case `GetClientHistory` to compile and return a client profile along with all their past chronological appointments and manual session notes owned by the authenticated `userId`.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer (Under TDD Cycle)

---

### Phase 4: Infrastructure, Persistence & Containerization
*Status: Pending*

#### [ ] TSK-012: Local Docker Containerization Setup (Dockerfile & docker-compose.yml)
*   **Description**: Create production-ready `Dockerfile` and `docker-compose.yml` orchestrating backend app and PostgreSQL database containers with local environment volume persistence [7, 26, 71].
*   **Proposed**: 2026-09-15 02:50 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: DevOps Engineer

#### [ ] TSK-013: SQL Database Schema Design & Migration Scripts
*   **Description**: Define relational SQL schema tables (`users`, `clients`, `appointments`, `session_notes`) using proper foreign keys, `user_id` indexes, and prepare migration scripts.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: Database Administrator

#### [ ] TSK-014: Implement Postgres Database Repositories (Adapters)
*   **Description**: Write concrete repository implementations (adapters) that fulfill `IClientRepository` and `IAppointmentRepository` interfaces with user-level isolation using SQLAlchemy or psycopg2.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: AI Developer

#### [ ] TSK-015: Configure Server-Side AuthN/AuthZ Middleware & Security Scans
*   **Description**: Implement HTTP authentication/authorization middleware verifying JWT/session tokens on every route, ensuring IDOR prevention and configuring SAST scanners (Bandit/CodeQL) [26, 66, 91].
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: Security Engineer

---

### Phase 5: Presentation & UI Layer (Web MVP)
*Status: Pending*

#### [ ] TSK-016: Set Up Web UI Interface & Login Screen (Gradio)
*   **Description**: Implement Gradio dashboard boilerplate with Login/Register forms and layout tabs for Client Registration, Scheduler, and Session Notes Review.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: UI Developer

#### [ ] TSK-017: Connect UI Forms to Application Use Cases
*   **Description**: Wire Gradio inputs (text fields, date pickers, dropdowns) directly into Hexagonal Core backend Use Cases with authenticated user context.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: Lead Developer

---

### Phase 6: Quality Verification & Project Delivery
*Status: Pending*

#### [ ] TSK-018: Execute Final Test Suite & Generate Coverage Report
*   **Description**: Run automated unit, integration, and security tests in Docker environment. Ensure code coverage is at or above the strict 85% requirement defined in DoD.
*   **Proposed**: 2026-09-07 11:57 (UTC)
*   **Started**: -
*   **Completed**: -
*   **Assignee**: QA Automation Engineer / CI pipeline

---

## 📝 Lifecycle Instructions for Devs and AI Agents

To update tasks in this file, follow these precise instructions:
1.  **Do not delete history**: Keep all completed and pending tasks to maintain a full audit trail [36, 38].
2.  **State progression**:
    *   When beginning a task: Change status to `[/] In Progress`, add current timestamp to `Started` and update **Sprint Dashboard** counts.
    *   When completing a task: Ensure all TDD tests are green, change status to `[x] Completed`, add current timestamp to `Completed`, update counts, and note down brief artifacts/outcomes in `Notes` section.
3.  **Ensure Traceability**: Always mention corresponding task IDs (`TSK-XXX`) in Git commit messages (e.g., `git commit -m "feat(domain): implement Client value objects (closes TSK-005)"`).
