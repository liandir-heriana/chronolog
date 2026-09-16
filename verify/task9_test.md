# TSK-009: Schedule Appointment Use Case with User Data Isolation

**Target / Task:** `TSK-009: Implement 'Schedule Appointment' Use Case with User Data Isolation`
**Module:** `src/modules/appointments/use_cases/` (depends only on domain ports)
**Assigned to:** `@backend-dev`
**SDD Route:** `skill({name:"sdd-apply"})` via `/apply TSK-009`

---

## 1. Domain Contracts & Invariants

The use-case layer is **100% pure Python (`stdlib` + domain only)**: zero imports of
`sqlalchemy`, `gradio`, `fastapi` in `domain/` **and** `use_cases/`.
The use case depends exclusively on the `IAppointmentRepository` +
`IClientRepository` ports (DIP). All reads are scoped by `user_id` (IDOR prevention).

### A. Window model (`src/modules/appointments/domain/entities.py`)

Appointments use the `starts_at / ends_at` window model (TSK-006 D1), **not**
`date_time + duration_minutes`. `Appointment.schedule(id, user_id, client_id,
starts_at, ends_at, *, now)` enforces:

*   **tz-aware:** `starts_at`, `ends_at`, and `now` must carry `tzinfo`;
    naive inputs raise `AppointmentValidationError`.
*   **ordered:** `ends_at > starts_at`, else `AppointmentValidationError`.
*   **future:** `starts_at >= now` (`now` explicit for testability);
    past starts raise `AppointmentValidationError`.
*   **refs:** `user_id` / `client_id` must be non-blank after `strip()`.

### B. Ports (`repository_interfaces.py`)

*   `IClientRepository.find_by_id_and_user_id(client_id: ClientId, user_id: str)
    -> Client | None` — sole ownership oracle for the booking target.
*   `IAppointmentRepository.list_overlapping(user_id, starts_at, ends_at,
    exclude_appointment_id=None) -> list[Appointment]` — half-open
    `[starts_at, ends_at)` semantics (`appt.starts_at < ends_at and starts_at <
    appt.ends_at`); scoped by `user_id`; `exclude_appointment_id` reserved for
    the self-update case (TSK-007 T7-D3).
*   `IAppointmentRepository.save(appointment)` — persists the new aggregate
    (owner carried inside `appointment.user_id`).

### C. Use case (`src/modules/appointments/use_cases/schedule_appointment.py`)

`ScheduleAppointment(appointments: IAppointmentRepository,
clients: IClientRepository)` (positional `ScheduleAppointment(repo, clients)`):

```python
def execute(
    self, *, user_id: str, client_id: str,
    starts_at: datetime, ends_at: datetime, now: datetime,
) -> Appointment: ...
```

Flow (AuthZ first, then validation, then persistence):

1.  `ClientId(client_id)` coercion — malformed UUIDs surface as
    `ClientValidationError` from the VO (same pattern as `RegisterUser`
    letting `UserEmail` raise).
2.  `clients.find_by_id_and_user_id(...)` — `None` (unknown id **or**
    other-user's client) raises `AppointmentValidationError("Client not found
    for user")`. No distinction between missing vs. foreign (no oracle).
3.  `Appointment.schedule(id=AppointmentId.generate(), user_id=user_id,
    client_id=client.id.value, starts_at=..., ends_at=..., now=now)` —
    reuses the canonical client id; window violations propagate as
    `AppointmentValidationError`.
4.  `appointments.list_overlapping(user_id, starts_at, ends_at)` — non-empty
    raises `AppointmentValidationError("Appointment overlaps an existing one")`.
    Adjacent (`ends_at == starts_at`) yields `[]` by half-open contract and is
    allowed; other users' windows never appear (scoped query).
5.  `appointments.save(appointment)` + return the entity (mirrors
    `RegisterUser.execute` returning the domain entity, no DTO layer in MVP).

Error taxonomy: **unified `AppointmentValidationError`** for all use-case
failures (unknown/foreign client, window, overlap) per the TSK-014 review note
(keep unified errors unless the audit mandates granular ones). See T9-D1.

### D. Purity & AuthZ

*   Imports: `datetime` (stdlib) + `Appointment` / `AppointmentId` /
    `AppointmentValidationError` / `IAppointmentRepository` + `IClientRepository`
    / `ClientId`. No `sqlalchemy | gradio | fastapi | infrastructure`.
*   Every access requires `user_id`: client lookup **and** overlap lookup are
    both scoped; `save` carries the owner. No `user_id`, no query.

---

## 2. Test Checklist (Given-When-Then / AAA)

All in `tests/modules/appointments/use_cases/test_schedule_appointment.py`
with in-memory fakes of both ports (`dict` keyed by `"user_id:uuid"`,
half-open overlap loop mirroring the TSK-007 contract test).

*   [ ] **success path** — Given a client owned by `user-1` and a free future
    window → When `execute(user_id="user-1", ...)` → Then an `Appointment`
    with matching `user_id` / canonical `client_id` / window is returned **and**
    round-trips via `find_by_id_and_user_id`.
*   [ ] **past start rejected** — Given `starts_at = now - 1h` → Then
    `AppointmentValidationError`, nothing persisted.
*   [ ] **end <= start rejected** — Given `ends_at == starts_at` → Then
    `AppointmentValidationError`, nothing persisted.
*   [ ] **naive datetimes rejected** — Given tz-naive `starts_at/ends_at`
    (tz-aware `now`) → Then `AppointmentValidationError`, nothing persisted.
*   [ ] **unknown client rejected** — Given a well-formed but unsaved
    `ClientId` → Then `AppointmentValidationError`, nothing persisted.
*   [ ] **other-user's client rejected (IDOR)** — Given a client owned by
    `user-owner` → When `execute(user_id="user-attacker", ...)` → Then
    `AppointmentValidationError`; neither attacker's nor owner's stores gain rows.
*   [ ] **overlapping same-user rejected** — Given a seeded `48h+1h` booking →
    When a `+30min` shifted overlap is requested → Then
    `AppointmentValidationError`, store stays at 1 row.
*   [ ] **adjacent allowed** — Given a seeded booking ending at `E` → When
    `starts_at == E` is requested → Then success, store grows to 2 rows.
*   [ ] **other user's overlap does NOT block** — Given `user-1`'s booking
    `[S, E)` and a `user-2`-owned client → When `user-2` books exactly
    `[S, E)` → Then success scoped to `user-2`.

---

## 3. Executable Test Reference (pointer, not a duplicate)

Full boilerplate lives in the repo — this guide does not duplicate it:

*   `src/modules/appointments/use_cases/schedule_appointment.py` — 21-line
    GREEN implementation (AuthZ → `schedule` → overlap → save).
*   `src/modules/appointments/use_cases/__init__.py` — re-exports
    `ScheduleAppointment` (mirrors `src/modules/auth/use_cases/__init__.py`).
*   `tests/modules/appointments/use_cases/__init__.py` — mirror package.
*   `tests/modules/appointments/use_cases/test_schedule_appointment.py` —
    9 tests with the two fakes:

```python
class InMemoryClientRepository(IClientRepository):
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[f"{client.user_id}:{client.id.value}"] = client

    def find_by_id_and_user_id(
        self, client_id: ClientId, user_id: str
    ) -> Client | None:
        return self._store.get(f"{user_id}:{client_id.value}")

    def list_by_user_id(self, user_id: str) -> list[Client]:
        return [c for c in self._store.values() if c.user_id == user_id]
```

```python
class InMemoryAppointmentRepository(IAppointmentRepository):
    def save(self, appointment: Appointment) -> None:
        self._store[f"{appointment.user_id}:{appointment.id.value}"] = appointment

    def list_overlapping(self, user_id, starts_at, ends_at,
                         exclude_appointment_id=None) -> list[Appointment]:
        result = []
        for appt in self._store.values():
            if appt.user_id != user_id:
                continue
            if exclude_appointment_id is not None and appt.id == exclude_appointment_id:
                continue
            if appt.starts_at < ends_at and starts_at < appt.ends_at:
                result.append(appt)
        return result
```

RED proof (pre-implementation): the new test module failed collection with
`ModuleNotFoundError: No module named 'src.modules.appointments.use_cases'`
before any production code was written; GREEN turned all 9 tests green with
no test edits.

Note: this file supersedes the stale draft previously at this path that
described a `date_time + duration_minutes` / `find_overlapping` /
`ClientNotFoundError` / `AppointmentOverlapError` design — that design
contradicts the TSK-006/007 review pointer (`starts_at/ends_at` + unified
`AppointmentValidationError` + `list_overlapping`) and the shipped
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

**Final verdict: the executed TSK-009 process is ACCEPTED — alignment with this verification proposal: ~100%.**

Breakdown (2026-09-16, executed implementation vs this guide):

*   **Contracts: 7/7 hold.** `starts_at/ends_at` window via `schedule`
    (tz-aware, ends>starts, past rejection, explicit `now`); dual-port DIP
    (`IClientRepository` ownership oracle + `IAppointmentRepository`
    half-open scoped overlap); keyword-only
    `execute(*, user_id, client_id, starts_at, ends_at, now) -> Appointment`;
    server-generated `AppointmentId`; canonical `client.id.value` persisted;
    unified `AppointmentValidationError` (malformed UUIDs honestly surface
    `ClientValidationError` from the VO); adjacent allowed, cross-user
    invisible.
*   **Checklist: 9/9 equivalent.** 9 new test functions across success /
    window (3) / ownership-IDOR (2) / overlap (3) classes; RED confirmed via
    collection-time `ModuleNotFoundError`; GREEN with zero test edits.
*   **Quality gates: 4/4 equivalent.** `pytest` 98 passed (89 prior + 9 new),
    total cov 95.14% (`schedule_appointment.py` itself 100%), `ruff` /
    `mypy` / `bandit` clean, boundary `grep` 0 matches on both `domain/` and
    `use_cases/`, Docker N/A as declared in Section 4.
    Independently re-verified 2026-09-16: 98 passed, 9/9 new, total cov 95.14%.

### Modeling Decision Log (TSK-009, 2026-09-16)

| # | Adopted decision | Spec alternative (§1) | Rationale | Status |
|---|---|---|---|---|
| T9-D1 | Unified `AppointmentValidationError` for unknown/foreign client + overlap + window | Granular `ClientNotFoundError` / `AppointmentOverlapError` / `AppointmentInPastError` (stale draft) | Keeps the TSK-014 D3 unified-error rule; one `ValueError` family for the whole booking flow; granular split only if TSK-015 audit mandates it | Accepted |
| T9-D2 | `execute(*, user_id, client_id, starts_at, ends_at, now) -> Appointment` (keyword-only, returns entity, no DTO) | `ScheduleAppointmentCommand` / `Response` DTOs (stale draft) | Mirrors `RegisterUser.execute(*, email, password) -> User`; no DTO layer exists in the codebase; DTO would be MVP over-engineering | Accepted |
| T9-D3 | `ScheduleAppointment(appointments, clients)` ctor order | `(appointment_repo, client_repo)` long names | Short plural names mirror `RegisterUser(users)`; positional `ScheduleAppointment(repo, clients)` per task brief still works | Accepted |
| T9-D4 | AuthZ first: client ownership → `schedule` → overlap → save | Window validation before ownership | Fail fast on IDOR without building objects; overlap never queried with invalid windows (naive datetimes rejected by `schedule` first) | Accepted |
| T9-D5 | `AppointmentId.generate()` server-side; persist canonical `client.id.value` | Caller-supplied id / raw `client_id` string | Prevents id spoofing; guarantees stored `client_id` equals the owned client's normalized UUID | Accepted |
| T9-D6 | Delegate interval math entirely to `list_overlapping` half-open `[S, E)`; no `exclude_appointment_id` on create | Reimplement overlap inline / `date_time + duration` | DIP: use case owns policy (reject on any hit), repo owns lookup; adjacent `ends==starts` allowed by contract; cross-user scoped out | Accepted |
| T9-D7 | `use_cases/` (underscore) package mirroring `auth/use_cases/` | `use-cases/` per AGENTS.md layout | Hyphen not Python-importable; same hexagonal role, rename is mechanical (cf. T8-D3) | Accepted |
| T9-D8 | Malformed `client_id` UUID propagates `ClientValidationError` unwrapped | Wrap everything as `AppointmentValidationError` | Honest input-shape error from the VO, same pattern as `RegisterUser` letting `UserEmail` raise; well-formed-but-foreign stays unified | Accepted |
