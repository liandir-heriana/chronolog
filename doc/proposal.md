# Final Project Proposal: ChronoLog - Appointment & Session Management App (MVP)

This document defines the formal development proposal for the Minimum Viable Product (MVP) of **ChronoLog**, a generalist **Appointment & Session Logging Application**. The design follows the principles of **Clean Architecture** and **Modular Monolith** taught in the course, establishing a robust, testable, and technical-debt-free foundation, fully prepared for future Artificial Intelligence integrations without compromising core business logic [15, 16].

---

## 1. Context & Business Problem

In professional service environments (consulting, legal, coaching, psychology, personal training, etc.), time management and accurate records of client interactions are critical. Common issues faced by professionals include:
- **Loss of Key Information**: Notes and summaries taken hastily after an appointment or meeting are often incomplete or unstructured.
- **Technology Coupling**: Traditional systems bind appointment logic to specific databases or rigid user interfaces, hindering future adaptation or integration [14, 15].
- **Lack of Traceability**: Absence of a continuous, secure, and chronological interaction history for each client [55].
- **Data Isolation & Access Control**: Risk of unauthorized access to sensitive client session data if strict authentication and authorization checks are missing on the server side [64, 90].

### Proposed Solution: ChronoLog
An MVP focused on solving the core problem: **scheduling appointments, persisting structured client profiles, and manually and securely recording session summaries and notes under strict user-level data isolation**.

*Note on architectural evolution:* While automated AI summarization remains a long-term goal, this MVP will initially be built as a pure traditional application (written notes entered manually by the professional). However, the software architecture will fully isolate *how* this summary is generated (using the Inversion of Dependencies Principle), enabling an AI adapter to be plugged in during a later phase without altering a single line of core business rules.

---

## 2. MVP Scope (MoSCoW Prioritization)

To guarantee successful project delivery within the strict timeframe of **2 to 4 weeks**, we apply the MoSCoW scoping framework [9]:

### MUST (Mandatory)
- **Client Registration**: Creation and maintenance of client profiles with basic contact data and strict input validation (emails, phone numbers, identifiers) [9].
- **Appointment Management (Scheduling)**: Creating, editing, and cancelling appointments, strictly preventing schedule overlaps for the same professional.
- **Continuous Session History**: Orderly, persistent, and chronological logging of past consultations/sessions for each client.
- **Manual Session Summary**: Rich-text entry for professionals to manually write meeting notes upon appointment completion [9].
- **Authentication & Authorization (AuthN/AuthZ)**: Secure user login and strict server-side authorization checks verifying resource ownership (`user_id`), preventing IDOR (Insecure Direct Object Reference) and ensuring strict multi-tenant data isolation [1, 22, 66, 79, 91].
- **Local Containerization (Docker Environment)**: Containerized deployment using Docker and `docker-compose.yml` for local execution, orchestrating backend services and a relational PostgreSQL database in an isolated, reproducible environment [7, 24, 26, 71].
- **Server-Side Validation & Environment Security**: Rigorous validation of all backend inputs and isolated configuration management via non-committed `.env` files [21, 56, 74].

### SHOULD (Highly Desirable)
- **Advanced Search**: Quick client filtering by name, identifier, or last session date range.
- **Calendar Agenda View**: An intuitive calendar-based visual interface (month/week/day) for seamless scheduling from the frontend.

### COULD (Optional / Nice-to-Have)
- **Session History Export**: Generating a secure, consolidated client history report in downloadable PDF format.
- **Local Reminders**: Simulation of automated local system notifications or emails for upcoming appointments.

### WON'T (Excluded from MVP)
- **AI-Powered Automated Summary**: Integration of external LLM APIs (OpenAI, Gemini) to summarize transcripts or unstructured notes is explicitly excluded from this phase to eliminate network dependencies, API subscription costs, and runtime latency [86].
- **External Cloud Deployment**: Cloud hosting is postponed; execution is confined to local Docker containers [7, 71].

---

## 3. Clean Architecture & Infrastructure Design

**ChronoLog** adopts a **Modular Monolith** style organized under **Clean Architecture (Hexagonal)** principles [16]. This ensures the business logic (Pure Domain) remains isolated from external infrastructure details (Databases, Web Frameworks, third-party APIs) [15].

### Local Containerized Infrastructure (Docker)
To avoid complex external hosting setups, the system is fully containerized using **Docker** and orchestrated with **Docker Compose** [7, 26, 71]:
- **App Container**: Running the Python backend and web presentation layer [26, 35].
- **Database Container**: Isolated PostgreSQL instance storing structured client, appointment, and authentication data [7, 71].
- **Environment Isolation**: Managed via `.env` templates (`.env.example` committed, `.env` git-ignored) [21, 74].

### Recommended Project Directory Structure

```text
src/
├── core/                               # Transversal shared code
│   └── shared/
│       ├── domain/                     # Global types, Value Objects, or global exceptions
│       ├── security/                   # AuthN/AuthZ middleware & token handlers
│       └── utils/
├── modules/                            # Highly cohesive modules (Modular Monolith)
│   ├── auth/                           # Authentication & User Account Module
│   ├── clients/                        # Clients Module
│   └── appointments/                   # Appointments and Summaries Module
│       ├── domain/                     # Domain Layer (Pure, free of external dependencies)
│       │   ├── entities/               # Appointment, SessionNotes, ClientHistory (Value Objects)
│       │   ├── repository-interfaces/  # IAppointmentRepository (Dependency Inversion)
│       │   └── exceptions/             # Business Exceptions (e.g., AppointmentOverlapException)
│       ├── use-cases/                  # Use Case Layer (Application Business Rules)
│       │   ├── ScheduleAppointment.ts
│       │   ├── CompleteAppointment.ts  # Binds manual summary to appointment
│       │   └── GetClientHistory.ts
│       └── infrastructure/             # Infrastructure Layer (Tech details and adapters)
│           ├── controllers/            # HTTP Controllers (Express/Fastify/Next.js/Gradio routes)
│           ├── persistence/            # PostgreSQL Adapters (SQLAlchemy/psycopg2)
│           │   └── PostgresAppointmentRepository.ts
│           └── external-services/      # Future home of the AI integration adapter
├── docker-compose.yml                  # Local container orchestration
├── Dockerfile                          # Backend container build instructions
└── main.ts / main.py                   # Application entry point (Composition Root)
```

### Dependency Inversion Principle (DIP) & Authorization Security

To ensure business rules and security checks do not depend on technical details, we apply the Dependency Inversion Principle (DIP) and validate authorization strictly at the server level [66, 91]:

```typescript
// src/modules/appointments/domain/repository-interfaces/IAppointmentRepository.ts
export interface IAppointmentRepository {
  findByIdAndUserId(id: string, userId: string): Promise<Appointment | null>;
  save(appointment: Appointment): Promise<void>;
}
```

By passing the authenticated `userId` to the repository port, the backend guarantees that professionals can only access or modify records belonging to their own account, preventing IDOR vulnerabilities [79, 91, 98].

---

## 4. Quality Roadmap & Software Life Cycle

To prevent technical debt from accumulating, the development process implements a structured **Spec-Driven Development (SDD)** [8] and **Test-Driven Development (TDD)** [27] flow. This is the ChronoLog instantiation. Methodology reference: `information.md` Section 3.

### SDD Flow Integrated into ChronoLog [8, 97]
1. **Explore & Propose**: Current phase of validating scope and functional requirements (consolidated in this document) [97].
2. **Spec ↔ Design**: Crafting formal specifications (OpenAPI/Swagger schemas, AuthN/AuthZ rules) and designing technical contracts before implementing code [63].
3. **Tasks**: Breaking down use cases and infrastructure setup into atomic, manageable tasks to keep context clear [63].
4. **Apply (Strict TDD Mode)**: Implementing each task sequentially using a test-first cycle [61]:
   - **RED**: Write a unit test describing expected business behavior or access restrictions and watch it fail [27, 63].
   - **GREEN**: Write the minimal production code necessary to pass the test [27].
   - **REFACTOR**: Clean up, optimize, and modularize code while keeping tests green [27].
5. **Verify**: Post-implementation validation using automated unit/integration tests and Docker container health checks [35, 99].
6. **Archive**: Formally closing iteration, recording technical discoveries in archive reports [102].

### Strict Definition of Done (DoD)
No user story or task is considered "Done" unless it satisfies the following gates [25]:
1. **Clean Compilation**: Zero compiler type errors or critical linter warnings.
2. **Testing Coverage**: 100% of associated tests passing, with a minimum code coverage of 85% in Domain and Use Case layers.
3. **Security & Data Isolation**: SAST passes without critical issues, credentials managed via `.env`, and all endpoints protected by server-side AuthN/AuthZ checks [21, 54, 66, 91].
4. **Containerization Verification**: Application and database services successfully build and run via `docker compose up` [7, 26].
5. **Documentation**: Self-documenting code with inline comments explaining complex decisions [1], and major architectural decisions recorded in local ADRs [30].

---

This proposal establishes a clear structure and a pragmatic framework to successfully complete **ChronoLog** on time, ensuring a clean, secure, and containerized engineering output [60, 96].
