# TSK-011: Get Client Interaction History Use Case

**Target / Task:** `TSK-011: Implement 'Get Client Interaction History' Use Case`
**Module:** `src/modules/appointments/use_cases/` (depends only on domain ports)
**Assigned to:** `@backend-dev`
**SDD Route:** `skill({name:"sdd-apply"})` via `/apply TSK-011`

---

## 1. Domain Contracts & Invariants

The use-case layer is **100% pure Python (`stdlib` + domain only)**: zero imports of
`sqlalchemy`, `gradio`, `fastapi` in `domain/` **and** `use_cases/`.
The use case depends exclusively on the `IClientRepository` + `IAppointmentRepository`
ports (DIP). Every access requires `user_id` (IDOR prevention).

### A. Entities (`clients/domain/entities.py`, `appointments/domain/entities.py`)

*   **`Client`** — aggregate root owned by one `user_id` (`id: ClientId`,
    `user_id`, `name`, `email: Email`, `phone: Phone | None`). Invariants in
    `__post_init__` / `update_contact`.
*   **`Appointment`** — aggregate root owned by one `user_id` (`id`, `user_id`,
    `client_id: str`, `starts_at / ends_at`, `status`). Window model
    (TSK-006 D1), **not** `date_time + duration_minutes`. Direct
    `Appointment(...)` allows past windows (only `ends_at > starts_at` +
    tz-aware checked); `Appointment.schedule(..., *, now)` additionally rejects
    `starts_at < now` — history seeds past rows via the constructor.
*   **`SessionNotes`** — bound to one completed appointment via
    `Appointment.attach_notes(content)` (allowed only when `COMPLETED`;
    empty/blank or `> 5000` chars raises `AppointmentValidationError`).
    Notes persist with the aggregate via `save` (no separate notes port
    methods, T10-D1).

### B. Ports (`repository_interfaces.py`)

*   `IClientRepository.find_by_id_and_user_id(client_id: ClientId, user_id: str)
    -> Client | None` — sole client-ownership oracle; `None` covers unknown id
    **and** foreign client (no oracle).
*   `IAppointmentRepository.list_by_client_and_user_id(client_id: str, user_id: str)
    -> list[Appointment]` — history source, already scoped by `user_id`
    (other users' rows with the same `client_id` string never leak).
*   No `save_session_notes` / `find_notes_by_*` — T7-D5 resolved as aggregate
    save (T10-D1); history performs **no separate notes lookup**.

### C. Use case (`src/modules/appointments/use_cases/get_client_history.py`)

`GetClientHistory(clients: IClientRepository, appointments: IAppointmentRepository)`
(positional `GetClientHistory(clients, appointments)`, client-first because the
profile is the primary lookup):

```python
@dataclass(frozen=True)
class ClientHistory:
    client: Client
    appointments: tuple[Appointment, ...]

def execute(self, *, user_id: str, client_id: str) -> ClientHistory: ...
```

Flow (AuthZ first, then scoped list, then ordering):

1.  `ClientId(client_id)` coercion — malformed UUIDs surface the VO's
    `ClientValidationError` (honest shape error, same pattern as T9-D8 /
    `AppointmentId` in T10).
2.  `clients.find_by_id_and_user_id(...)` — `None` (unknown id **or**
    other-user's client) raises
    `AppointmentValidationError("Client not found for user")` with a single
    shared message, byte-identical in both cases (no oracle, cf. TSK-009/010).
3.  `appointments.list_by_client_and_user_id(client.id.value, user_id)` —
    normalized `client.id.value` (not raw input) so UUID casing never misses;
    query is scoped by `user_id`.
4.  `tuple(sorted(history, key=lambda a: a.starts_at))` — chronological =
    **ascending** `starts_at` (past -> present). Sorting lives in the use case
    so any adapter order still returns chronologically.
5.  Return frozen `ClientHistory(client, appointments)` — empty tuple when zero
    appointments (not an error). No DTO layer in MVP (T9-D2, T11-D1): the
    profile is the `Client` entity, items are `Appointment` entities; a
    `COMPLETED` item proves its notes via `attach_notes` binding.

Error taxonomy: **unified `AppointmentValidationError`** for not-found/foreign
(D3/T9-D1, T11-D2). No `ClientNotFoundError`. Malformed-UUID
`ClientValidationError` propagates honestly (T11-D7).

### D. Purity & AuthZ

*   Imports: `dataclass`, `Appointment` / `AppointmentValidationError` /
    `IAppointmentRepository` / `Client` / `IClientRepository` / `ClientId`.
    No `sqlalchemy | gradio | fastapi | infrastructure`.
*   Every access requires `user_id`: client load scoped, appointment list
    scoped, normalized id reused. No `user_id`, no query.

---

## 2. Test Checklist (Given-When-Then / AAA)

All in `tests/modules/appointments/use_cases/test_get_client_history.py`
with in-memory fakes of both ports (`dict` keyed by `"user_id:uuid"`, mirroring
TSK-009/010). Past rows seed via direct `Appointment(...)` (schedule would
reject past); completed rows call `complete()` + `attach_notes()` to prove
notes binding (T10-D1).

*   [ ] **success path** — Given a client owned by `user-1` + 2 past rows
    (2-days-ago `COMPLETED` with `"  First session went well. "`, 1-day-ago
    `SCHEDULED`) → When `execute(user_id="user-1", client_id=...)` → Then
    `result.client == client`, `[a.id] == [first.id, second.id]` ascending,
    `result.appointments[0].status is COMPLETED`, and
    `result.appointments[0].attach_notes("First session went well.")` yields
    `appointment_id == first.id`, `user_id == "user-1"`, normalized content.
*   [ ] **unknown client rejected** — Given no matching row → Then
    `AppointmentValidationError`.
*   [ ] **foreign client rejected, same error (IDOR)** — Given a client owned
    by `user-owner` → When `execute(user_id="user-attacker", ...)` → Then
    `AppointmentValidationError` with a message **identical** to the
    unknown-id case (`str(foreign) == str(unknown)`).
*   [ ] **zero appointments → empty (not error)** — Given an owned client with
    no rows → Then `result.client == client` and
    `list(result.appointments) == []`.
*   [ ] **other user's appointments never leak** — Given one owned row +
    one row with the same `client_id` string but `user_id="user-2"` → Then
    history contains only the owned id and every item has
    `user_id == "user-1"`.
*   [ ] **unsorted seed still sorted ascending** — Given 3 rows seeded
    newest → oldest → middle (1, 3, 2 days ago) → Then ids return
    `[oldest, middle, newest]` and `starts == sorted(starts)`.

---

## 3. Executable Test Reference (pointer, not a duplicate)

Full boilerplate lives in the repo — this guide does not duplicate it:

*   `src/modules/appointments/use_cases/get_client_history.py` — GREEN
    implementation (coerce → AuthZ → scoped list → sort → frozen read model).
*   `src/modules/appointments/use_cases/__init__.py` — re-exports
    `ClientHistory, GetClientHistory` alongside `ScheduleAppointment`,
    `CompleteAppointment`.
*   `tests/modules/appointments/use_cases/__init__.py` — mirror package.
*   `tests/modules/appointments/use_cases/test_get_client_history.py` —
    6 tests with the dual-fake setup:

```python
class InMemoryClientRepository(IClientRepository):
    def save(self, client: Client) -> None:
        self._store[f"{client.user_id}:{client.id.value}"] = client

    def find_by_id_and_user_id(
        self, client_id: ClientId, user_id: str
    ) -> Client | None:
        return self._store.get(f"{user_id}:{client_id.value}")
```

```python
def _seed_past(appointments, *, user_id, client_id, days_ago,
               completed_with_notes=None) -> Appointment:
    starts_at, ends_at = _past_window(days_ago)
    appt = Appointment(id=AppointmentId.generate(), user_id=user_id,
                       client_id=client_id, starts_at=starts_at, ends_at=ends_at)
    if completed_with_notes is not None:
        appt.complete()
        notes = appt.attach_notes(completed_with_notes)
        assert notes.appointment_id == appt.id
    appointments.save(appt)
    return appt
```

RED proof (pre-implementation): the new test module failed collection with
`ModuleNotFoundError: No module named
'src.modules.appointments.use_cases.get_client_history'` before any
production code was written; GREEN turned all 6 tests green (one REFACTOR pass
simplified the foreign-client test to reuse the shared store, zero behavior
change).

Note: this file supersedes the stale draft previously at this path that
described `GetClientHistoryUseCase` / `ClientHistoryResponseDTO` /
`AppointmentHistoryItemDTO` / `SessionNoteDTO`, `ClientNotFoundError`,
`save_session_notes`, and a `date_time + duration_minutes` model — that design
contradicts the TSK-006/007 review pointer (`starts_at/ends_at` windows,
`attach_notes` factory + aggregate persistence), the adopted unified-error rule
(D3/T9-D1), the no-DTO style (T9-D2/T10-D4), and the shipped port signatures.

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

**Final verdict: the executed TSK-011 process is ACCEPTED — alignment with this verification proposal: ~100%.**

Breakdown (2026-09-16, executed implementation vs this guide):

*   **Contracts: 7/7 hold.** Dual-port DIP (`IClientRepository`,
    `IAppointmentRepository` only); keyword-only
    `execute(*, user_id, client_id) -> ClientHistory`; AuthZ via
    `find_by_id_and_user_id` with one shared not-found message (unknown ==
    foreign, asserted `==` in-test, no oracle); history via
    `list_by_client_and_user_id` on normalized `client.id.value` scoped by
    `user_id`; ascending `starts_at` sort in the use case; frozen
    `ClientHistory(client, appointments: tuple)` read model (no DTO layer);
    unified `AppointmentValidationError` (malformed UUIDs honestly surface the
    VO's `ClientValidationError`); notes via aggregate `attach_notes`, no new
    port methods.
*   **Checklist: 6/6 equivalent.** 6 test functions across success+binding (1)
    / IDOR (2) / empty (1) / isolation (1) / ordering (1); RED confirmed via
    collection-time `ModuleNotFoundError`; GREEN with one cosmetic REFACTOR
    (foreign-test simplification, no behavior change).
*   **Quality gates: 4/4 equivalent.** `pytest` 114 passed (108 prior + 6
    new), total cov 95.61% (`get_client_history.py` itself 100%), `ruff` /
    `mypy` (28 files) / `bandit` clean, boundary `grep` 0 matches on both
    `domain/` and `use_cases/`, Docker N/A as declared in Section 4.

### Modeling Decision Log (TSK-011, 2026-09-16)

| # | Adopted decision | Spec alternative (§1) | Rationale | Status |
|---|---|---|---|---|
| T11-D1 | Frozen `ClientHistory(client, appointments: tuple)` read model in `use_cases/`, no DTO layer (resolves "smallest honest shape" + T9-D2) | `ClientHistoryResponseDTO` / `AppointmentHistoryItemDTO` / `SessionNoteDTO` (stale draft §2) | No DTO layer exists in the codebase; `Schedule`/`Complete` return domain entities directly (T9-D2/T10-D4); a frozen dataclass in `use_cases/` keeps the pure `domain/` free of read shapes while staying explicit and `mypy`-safe; `tuple` communicates immutability | Accepted |
| T11-D2 | Unified `AppointmentValidationError("Client not found for user")` for unknown AND foreign client, asserted `==` in-test | `ClientNotFoundError` (stale draft §2) | Keeps the D3/T9-D1 unified-error rule; distinguishing missing vs. foreign leaks existence (oracle); message mirrors `ScheduleAppointment` so the appointments use-case family shares one error shape | Accepted |
| T11-D3 | Chronological = ascending `starts_at`, sorted in the use case | Descending timeline view (stale draft §1) | Ascending past→present is the natural audit trail and matches "chronological appointments"; sorting in the use case (not relying on adapter order) guarantees the contract for any TSK-014 adapter | Accepted |
| T11-D4 | Notes travel via the aggregate (`attach_notes`), no separate notes lookup (extends T10-D1, resolves T7-D5) | `save_session_notes` / `find_notes_by_*` + `SessionNoteDTO` join (stale draft §4) | Consistent with the `attach_notes` factory: the aggregate owns the notes lifecycle; keeps both ports minimal; avoids a second aggregate + second IDOR surface; history test proves binding via `attach_notes` on the returned `COMPLETED` item | Accepted |
| T11-D5 | Ctor `GetClientHistory(clients, appointments)` (client-first, short plural names) | `(appointment_repo, client_repo)` / `(appointment_repo, client_repo)` long names / appointments-first | Profile lookup is the primary step (fail-fast AuthZ before listing); short names mirror `ScheduleAppointment(appointments, clients)` / `RegisterUser(users)` / `CompleteAppointment(repo)` | Accepted |
| T11-D6 | History query uses normalized `client.id.value` from the loaded entity, not raw `client_id` input | Raw input string passed through | `ClientId` normalizes UUID casing via `str(UUID(...))`; reusing the entity value prevents a casing-mismatch miss between the AuthZ lookup and the history list | Accepted |
| T11-D7 | Malformed `client_id` surfaces `ClientValidationError` from the `ClientId` VO (honest shape error) | Unified into `AppointmentValidationError` | Same honest pattern as T9-D8 (`ClientId` in `ScheduleAppointment`) and T10 (`AppointmentId` in `CompleteAppointment`): shape errors stay distinguishable from not-found/foreign, which must stay unified for no-oracle | Accepted |
| T11-D8 | Zero appointments → empty `tuple`, not an error | Error on empty history | Profile exists and is owned; empty history is a valid state (new client); error would force callers to conflate "no client" with "no rows" | Accepted |
| T11-D9 | Lives in `src/modules/appointments/use_cases/` (with `Schedule`/`Complete`) | `src/modules/clients/use_cases/get_client_history.py` (stale draft header) | History items are appointments; colocating keeps the clients `domain/` pure and the appointments use-case family together; still depends on both ports via DIP, no boundary violation | Accepted |
| T11-D10 | Past rows seed via direct `Appointment(...)` constructor in tests | `Appointment.schedule(..., *, now)` for all seeds | `schedule` rejects `starts_at < now` by design; history is inherently about the past, and `__post_init__` already enforces tz-aware + ordered windows, so direct construction is the honest seeder | Accepted |
