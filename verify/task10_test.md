# TSK-010: Complete Appointment & Add Session Notes Use Case

**Target / Task:** `TSK-010: Implement 'Complete Appointment & Add Session Notes' Use Case`
**Module:** `src/modules/appointments/use_cases/` (depends only on domain ports)
**Assigned to:** `@backend-dev`
**SDD Route:** `skill({name:"sdd-apply"})` via `/apply TSK-010`

---

## 1. Domain Contracts & Invariants

The use-case layer is **100% pure Python (`stdlib` + domain only)**: zero imports of
`sqlalchemy`, `gradio`, `fastapi` in `domain/` **and** `use_cases/`.
The use case depends exclusively on the `IAppointmentRepository` port (DIP).
Every access requires `user_id` (IDOR prevention).

### A. Lifecycle + notes (`src/modules/appointments/domain/entities.py`)

`Appointment` owns the transition; `SessionNotes` is bound to one completed
appointment (TSK-006 D4):

*   **`complete()`** — `SCHEDULED -> COMPLETED` only; already-`COMPLETED` or
    `CANCELLED` raises `AppointmentValidationError("Only scheduled
    appointments can complete")`.
*   **`attach_notes(content)`** — allowed only when `status is COMPLETED`;
    creates `SessionNotes(id=SessionNoteId.generate(),
    appointment_id=self.id, user_id=self.user_id, content=normalized)`.
    Content is `strip()`-normalized; empty/blank or `> 5000` chars raises
    `AppointmentValidationError("Session notes content is invalid")`.
*   **Window model** — appointments use `starts_at / ends_at` (TSK-006 D1),
    **not** `date_time + duration_minutes`. Seeding in tests goes through
    `Appointment.schedule(..., *, now)` (tz-aware, `ends_at > starts_at`,
    `starts_at >= now`). The use case itself takes no window params.

### B. Port (`repository_interfaces.py`)

*   `IAppointmentRepository.find_by_id_and_user_id(appointment_id:
    AppointmentId, user_id: str) -> Appointment | None` — sole ownership
    oracle; `None` covers unknown id **and** foreign appointment (no oracle).
*   `IAppointmentRepository.save(appointment)` — persists the aggregate
    (owner carried inside `appointment.user_id`). **No `save_session_notes` /
    `find_notes_by_*` methods** — T7-D5 resolved as aggregate save (T10-D1):
    the `SessionNotes` created by `attach_notes` carries the validated, bound
    content for the infrastructure adapter to persist alongside the aggregate
    in TSK-013/014.

### C. Use case (`src/modules/appointments/use_cases/complete_appointment.py`)

`CompleteAppointment(appointments: IAppointmentRepository)` (positional
`CompleteAppointment(repo)`):

```python
def execute(
    self, *, appointment_id: str, user_id: str, content: str,
) -> Appointment: ...
```

Flow (AuthZ first, then lifecycle, then notes validation, then persistence):

1.  `AppointmentId(appointment_id)` coercion — malformed UUIDs surface as
    `AppointmentValidationError` from the VO (same honest shape-error pattern
    as T9-D8, where `ClientId` raises `ClientValidationError`).
2.  `appointments.find_by_id_and_user_id(...)` — `None` (unknown id **or**
    other-user's appointment) raises
    `AppointmentValidationError("Appointment not found for user")` with a
    single shared message, so both cases are byte-identical (no oracle).
3.  `appointment.complete()` — already-`COMPLETED` / `CANCELLED` propagates
    the domain `AppointmentValidationError`.
4.  `appointment.attach_notes(content)` — empty/blank/overlong propagates
    the domain `AppointmentValidationError`; success proves the notes are
    bound to the same `appointment_id` / `user_id` with normalized content.
5.  `appointments.save(appointment)` + return the entity (mirrors
    `ScheduleAppointment.execute` / `RegisterUser.execute` returning the
    domain entity, no DTO layer in MVP).

Error taxonomy: **unified `AppointmentValidationError`** for all use-case
failures (not-found/foreign, lifecycle, notes content) per D3/T9-D1. No
`AppointmentNotFoundError` / `EmptySessionNotesError` / `AppointmentStateError`.

### D. Purity & AuthZ

*   Imports: `Appointment` / `AppointmentValidationError` /
    `IAppointmentRepository` / `AppointmentId`. No `sqlalchemy | gradio |
    fastapi | infrastructure`.
*   Every access requires `user_id`: the single read is scoped; `save`
    carries the owner. No `user_id`, no query.

---

## 2. Test Checklist (Given-When-Then / AAA)

All in `tests/modules/appointments/use_cases/test_complete_appointment.py`
with an in-memory fake of the port (`dict` keyed by `"user_id:uuid"`, copy on
save/find/list so mutation without `save` never leaks — faithful to a real
adapter, see T10-D6).

*   [ ] **success path** — Given a `SCHEDULED` appointment owned by `user-1`
    → When `execute(appointment_id=..., user_id="user-1", content="  First
    session went well. ")` → Then an `Appointment` with the same id /
    `user_id` and `status is COMPLETED` is returned **and** round-trips via
    `find_by_id_and_user_id` as `COMPLETED`.
*   [ ] **notes bound to appointment/user** — Given the success result →
    Then `result.attach_notes("Progress noted.")` yields `appointment_id ==
    seed.id`, `user_id == "user-1"`, `content == "Progress noted."`.
*   [ ] **unknown id rejected** — Given no seeded row → Then
    `AppointmentValidationError`.
*   [ ] **foreign appointment rejected, same error (IDOR)** — Given a row
    owned by `user-owner` → When `execute(user_id="user-attacker", ...)` →
    Then `AppointmentValidationError` with a message **identical** to the
    unknown-id case; attacker's store stays empty, owner's row stays
    `SCHEDULED`.
*   [ ] **already-completed rejected** — Given a `COMPLETED` row → Then
    `AppointmentValidationError`.
*   [ ] **cancelled rejected** — Given a `CANCELLED` row → Then
    `AppointmentValidationError`; stored row stays `CANCELLED`.
*   [ ] **empty/blank notes rejected** — Given a `SCHEDULED` row → When
    `content in ("", "   ")` → Then `AppointmentValidationError`; stored row
    stays `SCHEDULED` (no `save` on the failure path).
*   [ ] **overlong notes rejected** — Given a `SCHEDULED` row → When
    `content == "x" * 5001` → Then `AppointmentValidationError`; stored row
    stays `SCHEDULED`.
*   [ ] **malformed id rejected** — Given `appointment_id == "nope"` → Then
    `AppointmentValidationError` from the `AppointmentId` VO.

---

## 3. Executable Test Reference (pointer, not a duplicate)

Full boilerplate lives in the repo — this guide does not duplicate it:

*   `src/modules/appointments/use_cases/complete_appointment.py` — GREEN
    implementation (AuthZ → `complete` → `attach_notes` → save).
*   `src/modules/appointments/use_cases/__init__.py` — re-exports
    `CompleteAppointment` alongside `ScheduleAppointment`.
*   `tests/modules/appointments/use_cases/__init__.py` — mirror package.
*   `tests/modules/appointments/use_cases/test_complete_appointment.py` —
    10 tests with the copy-semantics fake:

```python
class InMemoryAppointmentRepository(IAppointmentRepository):
    def save(self, appointment: Appointment) -> None:
        self._store[f"{appointment.user_id}:{appointment.id.value}"] = copy.copy(
            appointment
        )

    def find_by_id_and_user_id(
        self, appointment_id: AppointmentId, user_id: str
    ) -> Appointment | None:
        stored = self._store.get(f"{user_id}:{appointment_id.value}")
        return copy.copy(stored) if stored is not None else None
```

RED proof (pre-implementation): the new test module failed collection with
`ModuleNotFoundError: No module named
'src.modules.appointments.use_cases.complete_appointment'` before any
production code was written; GREEN turned all 10 tests green with no test
edits.

Note: this file supersedes the stale draft previously at this path that
described `CompleteAppointmentUseCase` / `CompleteAppointmentCommand` /
`Response` DTOs, `save_session_notes`, `AppointmentNotFoundError` /
`EmptySessionNotesError` / `AppointmentStateError`, and a `date_time +
duration_minutes` model — that design contradicts the TSK-006/007 review
pointer (`attach_notes` factory + aggregate persistence), the adopted
unified-error rule (D3/T9-D1), the no-DTO style (T9-D2), and the shipped
`Appointment.schedule` / port signatures.

---

## 4. Quality Gates

Before marking `[x]` in `doc/tasks.md`:

1.  **Tests + coverage:** `.venv/bin/pytest tests/ -q --cov=src --cov-fail-under=85`
2.  **Domain/use-case purity:**
    `grep -rE "sqlalchemy|gradio|fastapi" src/modules/*/domain` (0 matches) plus
    `grep -rE "sqlalchemy|gradio|fastapi" src/modules/appointments/use_cases
    src/modules/auth/use_cases` (0 matches)
3.  **Lint/types/scan:** `.venv/bin/ruff check src tests` +
    `.venv/bin/mypy src` + `.venv/bin/bandit -r src -q`
4.  **Docker:** N/A — no infrastructure in this task (deferred to TSK-012/014).

---

## 5. Parallel Verification Result (Justification)

**Final verdict: the executed TSK-010 process is ACCEPTED — alignment with this verification proposal: ~100%.**

Breakdown (2026-09-16, executed implementation vs this guide):

*   **Contracts: 6/6 hold.** Single-port DIP (`IAppointmentRepository`
    only); keyword-only `execute(*, appointment_id, user_id, content) ->
    Appointment`; AuthZ via `find_by_id_and_user_id` with one shared
    not-found message (unknown == foreign, asserted `==` in-test, no
    oracle); lifecycle delegated to `complete()`; notes delegated to
    `attach_notes()` (empty/blank/overlong + binding); aggregate `save`, no
    new port methods; unified `AppointmentValidationError` throughout
    (malformed UUIDs honestly surface the VO's `AppointmentValidationError`).
*   **Checklist: 10/10 equivalent.** 10 test functions across success+binding
    (2) / IDOR (2) / lifecycle (2) / notes validation (4) classes; RED
    confirmed via collection-time `ModuleNotFoundError`; GREEN with zero
    test edits.
*   **Quality gates: 4/4 equivalent.** `pytest` 108 passed (98 prior + 10
    new), total cov 95.34% (`complete_appointment.py` itself 100%), `ruff` /
    `mypy` (27 files) / `bandit` clean, boundary `grep` 0 matches on both
    `domain/` and `use_cases/`, Docker N/A as declared in Section 4.
    Independently re-verified 2026-09-16: 108 passed, 10/10 new, total cov
    95.34%.

### Modeling Decision Log (TSK-010, 2026-09-16)

| # | Adopted decision | Spec alternative (§1) | Rationale | Status |
|---|---|---|---|---|
| T10-D1 | Notes persist with the aggregate via `repo.save(appointment)`; no `save_session_notes` / `find_notes_by_*` on the port (resolves T7-D5) | Separate notes persistence methods (stale draft §1.4) | Consistent with the `attach_notes` factory (D4): the aggregate root owns the notes lifecycle; keeps the port minimal (5 methods); the validated `SessionNotes` is handed to the TSK-013/014 adapter inside `save`; avoids a second aggregate + second IDOR surface | Accepted |
| T10-D2 | Unified `AppointmentValidationError` for not-found/foreign + lifecycle + notes content | `AppointmentNotFoundError` / `EmptySessionNotesError` / `AppointmentStateError` (stale draft) | Keeps the D3/T9-D1 unified-error rule; one `ValueError` family for the whole completion flow; granular split only if the TSK-015 audit mandates it | Accepted |
| T10-D3 | `starts_at / ends_at` window model for seeding via `Appointment.schedule(..., *, now)` | `date_time + duration_minutes` constructor (stale draft template) | That model does not exist in the shipped domain (D1); `schedule` enforces tz-aware / ordered / future windows with explicit `now` for testability | Accepted |
| T10-D4 | Keyword-only `execute(*, appointment_id, user_id, content) -> Appointment`, no Command/Response DTOs; `content` matches `attach_notes(content)` / `SessionNotes.content` | `CompleteAppointmentCommand(session_notes_content)` / `CompleteAppointmentResponse(appointment_id, status, notes_id, updated_at)` (stale draft §2) | Mirrors `ScheduleAppointment.execute` / `RegisterUser.execute` returning the domain entity (T9-D2); no DTO layer exists in the codebase; DTO would be MVP over-engineering | Accepted |
| T10-D5 | Unknown id AND foreign appointment raise the identical message (`"Appointment not found for user"`), asserted `==` in-test; lifecycle/notes errors delegate to `complete()` / `attach_notes()` messages | Distinct not-found error disclosing existence (stale draft §1.1) | No-oracle rule (cf. TSK-009): distinguishing missing vs. foreign leaks existence to attackers; delegating messages keeps validation logic in the domain, not the use case | Accepted |
| T10-D6 | In-memory fake copies on `save` / `find` / `list` (`copy.copy`) | Reference-storing fake (TSK-009 style) | `complete()` mutates in place before `attach_notes` validation; with shared references a rejected-notes attempt would observably flip the stored row to `COMPLETED` before any `save` — copies emulate real adapter isolation so failure paths assert `SCHEDULED` | Accepted |
| T10-D7 | `CompleteAppointment(appointments)` single-repo ctor (short plural name) | `(appointment_repo)` long name / dual-repo ctor | Only the appointments port is needed (no client lookup on completion); short name mirrors `ScheduleAppointment(appointments, clients)` / `RegisterUser(users)` | Accepted |
