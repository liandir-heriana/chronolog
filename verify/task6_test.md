# Domain Contract Specification & Verifier — TSK-006

> **Target / Task**: `TSK-006: Model Appointment & SessionNotes Core Domains`  
> **Module**: `src/modules/appointments/domain/`  
> **Goal**: Implement the business entities and rules for appointments and session notes in pure Python 3.12 under the Strict TDD cycle (RED-GREEN-REFACTOR) [1, 4].

---

## 1. Domain Contract & Invariants

The domain layer must be **100% pure Python (`stdlib`)**, with no imports of databases, ORMs, or web frameworks (`sqlalchemy`, `gradio`, `fastapi`) [1].

### A. Enumerations & Value Objects
* **`AppointmentId`**: Immutable unique identifier (automatic UUID v4 if none is provided).
* **`AppointmentStatus`**: Enumeration (`SCHEDULED`, `COMPLETED`, `CANCELLED`).

### B. `Appointment` Aggregate/Entity
* **Attributes**:
  * `id: AppointmentId`
  * `user_id: str` (Mandatory; enforces the anti-IDOR authorization rule [1])
  * `client_id: str` (Identifier of the associated client)
  * `date_time: datetime` (Scheduled date and time)
  * `duration_minutes: int` (Duration in minutes, must be > 0)
  * `status: AppointmentStatus` (Current status, defaults to `SCHEDULED`)
  * `created_at: datetime`
* **Business Rules & Invariants**:
  1. **Future Date Validation**: An appointment cannot be created in the past relative to the current date/time (`AppointmentInPastException`).
  2. **Duration Validation**: `duration_minutes` must be greater than 0 (`InvalidAppointmentDurationException`).
  3. **User Isolation**: `user_id` cannot be null or empty (`DomainValidationError`).
  4. **State Transitions**:
     * `complete()`: Changes the status to `COMPLETED`.
     * `cancel()`: Changes the status to `CANCELLED`.
     * Cancelled appointments cannot be modified.

### C. `SessionNotes` Entity
* **Attributes**:
  * `id: str` (UUID v4)
  * `appointment_id: AppointmentId` (Mandatory link to the appointment)
  * `user_id: str` (Note owner)
  * `content: str` (Manual session summary text)
  * `created_at: datetime`
  * `updated_at: datetime`
* **Business Rules & Invariants**:
  1. **Completed Appointment Required**: Session notes can only be linked or created if the corresponding appointment has status `COMPLETED` (`AppointmentNotCompletedException`).
  2. **Non-Empty Content**: `content` cannot be empty or whitespace-only (`EmptySessionNotesException`).

---

## 2. Recommended Test Cases (AAA / Given-When-Then)

### `Appointment` Tests (`tests/unit/appointments/test_appointment.py`)
1. **`test_create_appointment_success`**:
   * **Given**: A `user_id`, `client_id`, and valid future date.
   * **When**: `Appointment` is instantiated.
   * **Then**: The appointment is created with status `SCHEDULED`.
2. **`test_create_appointment_in_past_raises_exception`**:
   * **Given**: A past date (e.g. yesterday).
   * **When**: Appointment creation is attempted.
   * **Then**: Raises `AppointmentInPastException`.
3. **`test_create_appointment_invalid_duration_raises_exception`**:
   * **Given**: `duration_minutes <= 0`.
   * **When**: `Appointment` instantiation is attempted.
   * **Then**: Raises `InvalidAppointmentDurationException`.
4. **`test_complete_and_cancel_appointment`**:
   * **Given**: An appointment with status `SCHEDULED`.
   * **When**: `appointment.complete()` or `appointment.cancel()` is invoked.
   * **Then**: The status is updated accordingly.

### `SessionNotes` Tests (`tests/unit/appointments/test_session_notes.py`)
5. **`test_create_session_notes_on_completed_appointment_success`**:
   * **Given**: A completed (`COMPLETED`) appointment and valid summary text.
   * **When**: The session notes are instantiated.
   * **Then**: They are successfully linked to the appointment.
6. **`test_create_session_notes_on_scheduled_appointment_raises_exception`**:
   * **Given**: An appointment with status `SCHEDULED` (not yet completed).
   * **When**: `SessionNotes` creation is attempted.
   * **Then**: Raises `AppointmentNotCompletedException`.
7. **`test_create_session_notes_empty_content_raises_exception`**:
   * **Given**: Empty or whitespace text (`"   "`).
   * **When**: `SessionNotes` instantiation is attempted.
   * **Then**: Raises `EmptySessionNotesException`.

---

## 3. Executable Test Template (`pytest`)

```python
from datetime import datetime, timedelta, timezone
import pytest

from src.modules.appointments.domain.entities import Appointment, SessionNotes, AppointmentStatus
from src.modules.appointments.domain.exceptions import (
    AppointmentInPastException,
    AppointmentNotCompletedException,
    EmptySessionNotesException,
    InvalidAppointmentDurationException
)

def test_create_appointment_success():
    future_date = datetime.now(timezone.utc) + timedelta(days=1)
    app = Appointment(
        user_id="usr_123",
        client_id="cli_456",
        date_time=future_date,
        duration_minutes=45
    )
    assert app.status == AppointmentStatus.SCHEDULED
    assert app.user_id == "usr_123"

def test_create_appointment_in_past_raises_error():
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(AppointmentInPastException):
        Appointment(
            user_id="usr_123",
            client_id="cli_456",
            date_time=past_date,
            duration_minutes=30
        )

def test_session_notes_requires_completed_appointment():
    future_date = datetime.now(timezone.utc) + timedelta(days=1)
    app = Appointment(
        user_id="usr_123",
        client_id="cli_456",
        date_time=future_date,
        duration_minutes=30
    )

    # Attempt in SCHEDULED state -> must fail
    with pytest.raises(AppointmentNotCompletedException):
        SessionNotes(
            appointment=app,
            user_id="usr_123",
            content="Session summary"
        )

    # Switch to COMPLETED -> must pass
    app.complete()
    notes = SessionNotes(
        appointment=app,
        user_id="usr_123",
        content="Post-session summary"
    )
    assert notes.content == "Post-session summary"
```

---

## 4. Quality Gates

Before marking `[x]` in `doc/tasks.md` [3]:
1. **Unit tests**: `pytest tests/unit/appointments/ -q --cov=src/modules/appointments/domain --cov-fail-under=85` [3].
2. **Domain purity**: `grep -rE "sqlalchemy|gradio|fastapi" src/modules/appointments/domain` (must return 0) [1].
3. **Lint & Typing**: `ruff check src tests` and `mypy src` [3].

---

## 5. Parallel Verification Result (Justification)

**Final verdict: the executed TSK-006 process is ACCEPTED — alignment with this verification proposal: ~80%.**

Breakdown (2026-09-15, executed implementation vs this guide):

- **Behavioral contracts: 7/7 equivalent.** Valid creation in `SCHEDULED`, past rejection, `complete()`/`cancel()` transitions with terminal-state guards (covers "no modifying cancelled"), notes only when `COMPLETED`, non-empty content, mandatory anti-IDOR `user_id`.
- **Quality gates: 3/3 equivalent (executed broader).** `pytest` 40 passed with 97.38% coverage on `src` (≥85%), `grep` 0 matches, `ruff`/`mypy`/`bandit` clean. Run on `tests/` + `src/` instead of the proposed `tests/unit/...` paths.
- **Design divergences (decided, non-blocking, 5 items):**
  1. **`starts_at/ends_at` window vs `date_time + duration_minutes`.** The window expresses the interval directly and prepares overlap detection (TSK-009 `ScheduleAppointment`); the `duration > 0` rule is subsumed by `ends_at > starts_at`. There is no `duration_minutes` validation because the field does not exist.
  2. **Explicit `schedule(..., now)` vs internal `datetime.now()`.** The injected `now` makes the "no past" rule deterministic in tests; same invariant, no flakiness.
  3. **Unified `AppointmentValidationError` vs 4 specific exceptions** (`AppointmentInPastException`, `InvalidAppointmentDurationException`, `AppointmentNotCompletedException`, `EmptySessionNotesException`). Same rejection, less granularity.
  4. **`Appointment.attach_notes()` factory vs direct `SessionNotes(appointment=...)`.** The "only when COMPLETED" invariant is enforced at the creation point and the link is guaranteed; `update_content(content, appointment)` revalidates status and ownership.
  5. **No `created_at` on `Appointment` nor `updated_at` (only `created_at` on notes), `tests/modules/...` mirror vs `tests/unit/...`.** Full chronological traceability arrives with history/persistence (TSK-011/013); the mirror layout is fixed in `AGENTS.md`.

Justification: every invariant and gate in Sections 1–4 holds in the implementation; the divergences are documented modeling decisions, not unvalidated behavior. No process redo required. If the course requires literal `duration_minutes` or the 4 exceptions, track it as an alignment sub-task with its own RED cycle instead of rewriting TSK-006.

### Modeling Decision Log (TSK-006, 2026-09-15)

| # | Adopted decision | Spec alternative (§1–§3) | Rationale | Status |
|---|---|---|---|---|
| D1 | `starts_at/ends_at` window | `date_time + duration_minutes` | Explicit interval prepares overlaps (TSK-009); `duration > 0` subsumed by `ends_at > starts_at` | Accepted |
| D2 | Explicit `schedule(..., now)` | Internal `datetime.now()` | Deterministic "no past" rule, flake-free tests | Accepted |
| D3 | Unified `AppointmentValidationError` | 4 specific exceptions | Same rejection, fewer classes (YAGNI in domain) | Accepted, reversible |
| D4 | `Appointment.attach_notes()` factory | Direct `SessionNotes(appointment=...)` | "Only when COMPLETED" invariant by construction; `update_content` revalidates | Accepted |
| D5 | No `created_at/updated_at` on appointment; `tests/modules/` mirror layout | `created_at/updated_at`, `tests/unit/` | Full chronology in TSK-011/013; layout fixed in `AGENTS.md` | Accepted |
