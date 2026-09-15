# ADR-001: Architectural Style - ChronoLog Modular Monolith with Hexagonal/Clean Architecture

## Status
**Accepted**

## Date
2026-09-07

## Context
The **ChronoLog** project requires building a robust, maintainable, and scalable generalist Appointment & Session Management MVP within a strict timeline of 2 to 4 weeks. Key architectural risks include:
- **Early over-engineering**: Introducing complex structures (like microservices) prematurely can derail the timeline and introduce operational overhead.
- **Technical debt accumulation**: A chaotic "Big Ball of Mud" structure would make future scalability, maintenance, and the integration of automated features (such as AI summary generation) extremely difficult and costly.
- **Tightly coupled components**: Coupling core business logic directly to databases, third-party frameworks, or specific user interfaces restricts long-term technical evolution.

To resolve these challenges, we must establish a clear architectural pattern that balances initial delivery speed with clean, logical separation of concerns.

## Decision
We decided to adopt a **Modular Monolithic Architectural Style** organized around **Hexagonal/Clean Architecture** principles for **ChronoLog**.

### Key Architectural Guidelines:
1. **Cohesive Modules**: The monolith is split into distinct, highly cohesive modules (e.g., `clients`, `appointments`) that manage their own logic and boundaries.
2. **Hexagonal (Clean) Structure**: Each module isolates its pure **Domain** (Entities, Value Objects, and Domain Exceptions) and **Use Cases** (Application Rules) from the outer **Infrastructure** layer (Databases, Web Frameworks, and External Adapters).
3. **Inversion of Dependencies (DIP)**: Dependencies must point inward toward the core domain. Infrastructure components implement interfaces (ports) defined by the domain.
4. **Local Integration**: Communication between modules will occur via clean public interfaces or internal synchronous events (pub/sub), avoiding microservices network overhead.

## Alternatives Considered

### Option A: Microservices Architecture
- **Pros**: Organizational scalability, independent deployment, isolated failures.
- **Cons**: Extremely high operational overhead (infrastructure setup, CI/CD, service discovery), data consistency challenges, and network latency. Too complex for a 2-4 week MVP scope. 
- *Verdict*: **Rejected** as an early over-engineering anti-pattern.

### Option B: Traditional "All-in-One" Monolith (Unstructured)
- **Pros**: Fastest initial setup and development.
- **Cons**: High risk of creating a "Big Ball of Mud" with tightly coupled code. Leads to fast-building technical debt, rendering future AI integration and testing highly complex.
- *Verdict*: **Rejected** due to long-term high cost of change and debt accumulation.

### Option C: Modular Monolith with Hexagonal/Clean Architecture
- **Pros**: Balances the rapid delivery of a monolith with the logical separation of microservices. Domain code remains highly testable and completely isolated from database engines (Supabase/PostgreSQL) and future AI service adapters.
- **Cons**: Requires strict architectural discipline and code reviews to prevent developers from taking shortcuts that bypass module boundaries.
- *Verdict*: **Selected** as the pragmatic, scalable, and highly maintainable approach for ChronoLog.

## Justification
This hybrid approach provides high-level modular boundaries, making the code easy to read, test, and adapt. Testing can be written in a true test-first (TDD) fashion without relying on external databases. If a module encounters performance bottlenecks or scaling demands in the future, its clear boundaries make it simple to extract into an independent microservice with minimal code changes.

## Consequences
- **Positive**:
  - High testing speed (unit tests don't require database connections or server boots).
  - High flexibility to swap infrastructure (e.g., changing from a local PostgreSQL to a cloud-based Supabase instance requires no domain code modification).
  - Preparation for future AI summaries is simplified; we only need to write a new adapter in the infrastructure layer.
- **Negative**:
  - Slightly more boilerplate code initially due to interfaces (ports) and adapters.
  - Requires automated rules or thorough PR reviews to enforce boundary isolation and prevent unauthorized database reads across modules.
