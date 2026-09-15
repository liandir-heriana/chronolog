# ChronoLog Project Information & Reference Guide

This document provides a concise English summary of the **ChronoLog** MVP application project (Appointment & Session Management Platform), compiling the strategic and development guidelines established from our architectural discussions and the course methodology.

## 1. Project Core & Architectural Philosophy

The goal is to build **ChronoLog** as an **Appointment & Session Management MVP** (initially without direct AI integration) with high quality standards, domain generalizability (supporting consultancies, coaching, clinics, legal, and professional services), and zero technical debt.

### Core Architecture
*   **Modular Monolith**: We start with a highly organized Modular Monolith. It avoids the operational overhead and early complexity of microservices while ensuring clean, logical boundaries [17].
*   **Clean & Hexagonal Architecture**: Separation of concerns is strictly enforced. The pure **Domain Layer** (business rules and entities) is fully isolated and does not depend on databases, frameworks, or presentation details [7, 10].
*   **Inversion of Dependencies (DIP)**: High-level modules do not depend on low-level modules; both depend on abstractions. This ensures that tomorrow, replacing a database or adding an automated AI summary generator is simply a matter of infrastructure adapters without touching the core business logic.

---

## 2. Web MVP Development Tools

To deliver a functional web application in **2 to 4 weeks**, we leverage advanced generative tools to accelerate our presentation and infrastructure setup:

*   **v0 (by Vercel)**: Used for rapid frontend UI generation using simple prompts, images, or mockups [30]. It auto-publishes responsive designs directly to Vercel, drastically reducing maquetation time [30].
*   **Lovable**: A powerful tool to build full web MVPs [31]. It allows importing images or documents to draft functional components, supports AI-assisted component editing, provides built-in security scans, and automatically connects to a **Supabase (PostgreSQL)** backend for instant database integration [31].
*   **Gradio (Alternative / Python Híbrido)**: If a fast Python-driven web interface is preferred, Gradio provides instant UI components (forms, tables, buttons) directly coupled to Python scripts with minimal frontend code, facilitating future AI integration [72, 118].

---

## 3. High-Rigor Development Process (SDD & TDD)

We follow the **Spec-Driven Development (SDD)** framework and **Test-Driven Development (TDD)** to ensure structural integrity and code quality:

### Spec-Driven Development (SDD) — The 9 Phases [63]
1.  **explore**: Investigate the current context, codebase, and business needs [114].
2.  **propose**: Draft a formal project proposal (like our `proposal-v3.md`) specifying goals, non-goals, and MoSCoW scope [114].
3.  **spec**: Define technical requirements, schemas (JSON/OpenAPI), and strict business rules [63].
4.  **design**: Establish architectural designs, data models, and module contracts [63].
5.  **tasks**: Break down the design and specs into small, atomic, and clear tasks to prevent model amnesia [63].
6.  **apply**: Write tests and implement code in small, coherent batches [63].
7.  **verify**: Check the implementation against each acceptance criterion [64, 115].
8.  **archive**: Record the technical and decision histories for future scalability [115].

### Strict TDD (RED-GREEN-REFACTOR) [63]
Within the **sdd-apply** phase, the development cycle is strictly test-first:
*   **RED**: Write a failing test describing the desired behavior before writing any production code [63].
*   **GREEN**: Write the minimal amount of code necessary to make the test pass [63].
*   **REFACTOR**: Clean up, optimize, and modularize the code while keeping the tests green [63].

---

## 4. AI-Assisted Development & Team Governance

As the human orchestrator directing the AI, we establish solid guardrails to enforce architectural purity:

*   **AGENTS.md**: Located in the project root, this file serves as the "README for AI Agents" [39]. It provides the system context, architectural constraints (Modular Hexagonal rules), code style preferences, and "source of truth" documentation to the IDE copilot (e.g., Cursor, VS Code, Windsurf) [39, 42]. This keeps the AI from hallucinating or inventing code that doesn't respect our Clean Architecture [36].
*   **Code Scanning & Dependency Guardrails**: Set up automated Quality Gates such as **CodeQL** (to detect vulnerabilities and bad practices) [26] and **Dependabot** (to monitor and patch vulnerable libraries) [26] inside the CI/CD pipeline.
