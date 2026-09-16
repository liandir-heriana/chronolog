# TSK-007: Define Domain Repository Ports (Interfaces)

**Target / Task:** `TSK-007: Define Domain Repository Ports (Interfaces)`  
**Module:** `src/modules/clients/domain/` & `src/modules/appointments/domain/`  
**Assigned to:** `@backend-dev`  
**SDD Route:** `skill({name:"sdd-apply"})` via `/apply TSK-007`  

---

## 1. Design Context & Principles (Clean / Hexagonal Architecture)

In Hexagonal Architecture, the Domain Core must not know infrastructure details (databases, ORMs like SQLAlchemy, raw SQL, etc.) [50]. To achieve this, the Domain defines its **Outbound Ports** (*Ports* / Interfaces) using pure Python abstract classes (`abc.ABC`).

### Key Rules:
1. **Dependency Inversion (DIP)**: Use cases depend exclusively on the abstractions (`IClientRepository`, `IAppointmentRepository`), never on PostgreSQL or SQLAlchemy [1, 2].
2. **Anti-IDOR Data Isolation (Strict AuthZ)**: Every query or mutation defined in the ports MUST explicitly include the `user_id: str` parameter (e.g. `find_by_id_and_user_id`) [2]. Defining `find_by_id` methods without `user_id` is forbidden.
3. **Domain Purity**: Zero external imports (`sqlalchemy`, `gradio`, `fastapi`, `pydantic`). Only the Python standard library (`abc`, `typing`, `datetime`, `uuid`) and the domain's own Value Objects / Entities [1, 2].

---

## 2. Domain Port Contracts

### A. Clients Port: `IClientRepository`
*Proposed location:* `src/modules/clients/domain/ports.py`

```python
from abc import ABC, abstractmethod
from typing import Optional, List
from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.value_objects import ClientId

class IClientRepository(ABC):
    @abstractmethod
    def save(self, client: Client) -> None:
        """Persist or update a client in storage."""
        pass

    @abstractmethod
    def find_by_id_and_user_id(self, client_id: ClientId, user_id: str) -> Optional[Client]:
        """Find a client by ID while guaranteeing user_id ownership (Anti-IDOR)."""
        pass

    @abstractmethod
    def list_by_user_id(self, user_id: str) -> List[Client]:
        """Retrieve the list of clients belonging to the authenticated professional."""
        pass

    @abstractmethod
    def delete_by_id_and_user_id(self, client_id: ClientId, user_id: str) -> bool:
        """Delete a client guaranteeing user_id ownership. Returns True if it existed."""
        pass
```

### B. Appointments & Notes Port: `IAppointmentRepository`
*Proposed location:* `src/modules/appointments/domain/ports.py`

```python
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime
from src.modules.appointments.domain.entities import Appointment, SessionNotes
from src.modules.appointments.domain.value_objects import AppointmentId

class IAppointmentRepository(ABC):
    @abstractmethod
    def save(self, appointment: Appointment) -> None:
        """Persist or update an appointment in storage."""
        pass

    @abstractmethod
    def find_by_id_and_user_id(self, appointment_id: AppointmentId, user_id: str) -> Optional[Appointment]:
        """Retrieve an appointment by ID validating user_id ownership (Anti-IDOR)."""
        pass

    @abstractmethod
    def list_by_user_id(self, user_id: str) -> List[Appointment]:
        """Get all appointments belonging to the authenticated user."""
        pass

    @abstractmethod
    def list_by_client_id_and_user_id(self, client_id: str, user_id: str) -> List[Appointment]:
        """Get the appointment history of a specific client of the user."""
        pass

    @abstractmethod
    def find_overlapping(
        self, 
        user_id: str, 
        date_time: datetime, 
        duration_minutes: int, 
        exclude_appointment_id: Optional[AppointmentId] = None
    ) -> List[Appointment]:
        """Find existing appointments overlapping in time for the same professional."""
        pass

    @abstractmethod
    def save_session_notes(self, notes: SessionNotes) -> None:
        """Persist the manual session notes linked to an appointment."""
        pass

    @abstractmethod
    def find_notes_by_appointment_id_and_user_id(
        self, 
        appointment_id: AppointmentId, 
        user_id: str
    ) -> Optional[SessionNotes]:
        """Retrieve the session notes of an appointment verifying the user_id."""
        pass
```

---

## 3. Contract Unit Test Battery (Strict TDD / In-Memory Repositories)

To test the ports before wiring PostgreSQL in Phase 4, in-memory implementations (`InMemoryClientRepository`, `InMemoryAppointmentRepository`) are created in the test layer.

### Given-When-Then Scenarios:

1. **`test_client_repository_save_and_find_success`**:
   * **Given**: An instantiated client for `user_id = "user_123"`.
   * **When**: It is saved to the repository and queried via `find_by_id_and_user_id(client.id, "user_123")`.
   * **Then**: Returns the exact `Client` entity.

2. **`test_client_repository_anti_idor_isolation`**:
   * **Given**: A client belonging to `user_123`.
   * **When**: Another user (`user_999`) tries to retrieve it via `find_by_id_and_user_id(client.id, "user_999")`.
   * **Then**: Returns `None` (strict data isolation).

3. **`test_appointment_repository_find_overlapping`**:
   * **Given**: An appointment scheduled for `user_123` on 2026-10-01 at 10:00 (60 min duration).
   * **When**: `find_overlapping` is queried for the same `user_123` at 10:30 (30 min duration).
   * **Then**: Returns the conflicting appointment. Verified that for another `user_456` at the same time there is no overlap.

---

## 4. Executable Test Template (`tests/unit/shared/test_repository_ports.py`)

```python
import pytest
from datetime import datetime, timedelta
from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.value_objects import ClientId, Email, Phone
from src.modules.appointments.domain.entities import Appointment, SessionNotes
from src.modules.appointments.domain.value_objects import AppointmentId, AppointmentStatus
from src.modules.clients.domain.ports import IClientRepository
from src.modules.appointments.domain.ports import IAppointmentRepository

class InMemoryClientRepository(IClientRepository):
    def __init__(self):
        self._storage = {}

    def save(self, client: Client) -> None:
        self._storage[(str(client.id), client.user_id)] = client

    def find_by_id_and_user_id(self, client_id: ClientId, user_id: str):
        return self._storage.get((str(client_id), user_id))

    def list_by_user_id(self, user_id: str):
        return [c for (_, u_id), c in self._storage.items() if u_id == user_id]

    def delete_by_id_and_user_id(self, client_id: ClientId, user_id: str) -> bool:
        key = (str(client_id), user_id)
        if key in self._storage:
            del self._storage[key]
            return True
        return False

def test_client_repository_contract_and_idor_protection():
    repo = InMemoryClientRepository()
    client = Client(
        user_id="user_owner",
        full_name="Juan Pérez",
        email=Email("juan@example.com"),
        phone=Phone("+34600111222")
    )
    
    repo.save(client)
    
    # Success: correct owner
    found = repo.find_by_id_and_user_id(client.id, "user_owner")
    assert found is not None
    assert found.full_name == "Juan Pérez"
    
    # Anti-IDOR block: foreign user
    idor_attempt = repo.find_by_id_and_user_id(client.id, "user_attacker")
    assert idor_attempt is None
```

---

## 5. Quality Gates

To consider **`TSK-007`** completed (`[x]`), OpenCode will verify:

1. **Domain Layer Purity**:
   ```bash
   grep -rE "sqlalchemy|gradio|fastapi|psycopg2" src/modules/*/domain/
   # Expected result: 0 matches
   ```
2. **Test Coverage**:
   ```bash
   pytest tests/unit/ -q --cov=src/modules --cov-fail-under=85
   ```
3. **Static Code Control**:
   ```bash
   ruff check src/ tests/ && mypy src/
   ```

---

## 6. Parallel Verification Result (Justification)

**Final verdict: the executed TSK-007 process is ACCEPTED — alignment with this verification proposal: ~80%.**

Breakdown (2026-09-16, executed implementation vs this guide):

- **Key rules: 3/3 hold.** DIP (ports are ABCs in `domain/`, use-case-ready), strict AuthZ (every read scoped by `user_id`, no bare `find_by_id` anywhere), domain purity (stdlib + domain imports only, boundary `grep` 0 matches).
- **Contract scenarios: 3/3 equivalent.** Save-and-find round-trip, anti-IDOR isolation (`None` for foreign `user_id`), overlap lookup returning conflicts for the same user and none for another user — all covered by the 11 executed port tests (in-memory fakes in the test layer, as proposed in Section 3).
- **Quality gates: 3/3 equivalent (executed broader).** `pytest` 51 passed with 94.30% coverage on `src` (≥85%), `ruff`/`mypy`/`bandit` clean. Run on `tests/` + `src/` instead of the proposed `tests/unit/` + `src/modules` paths.
- **Method divergences (decided, non-blocking, 5 items):** `repository_interfaces.py` vs proposed `ports.py`; `list_by_client_and_user_id` vs proposed `list_by_client_id_and_user_id`; window-based `list_overlapping(user_id, starts_at, ends_at, ...)` vs proposed `find_overlapping(user_id, date_time, duration_minutes, ...)`; no `delete_by_id_and_user_id`; no `save_session_notes` / `find_notes_by_appointment_id_and_user_id`.

Justification: every rule, scenario, and gate in Sections 1–5 holds in the implementation; the divergences are documented modeling decisions, not unvalidated behavior. No process redo required. The three deferred methods (`delete_*`, `save_session_notes`, `find_notes_by_*`) become alignment sub-tasks with their own RED cycle if and when a use-case requires them (TSK-010/014), instead of rewriting TSK-007.

### Modeling Decision Log (TSK-007, 2026-09-16)

| # | Adopted decision | Spec alternative (§2) | Rationale | Status |
|---|---|---|---|---|
| T7-D1 | File `repository_interfaces.py` | `ports.py` | Matches existing domain module naming (`entities.py`, `value_objects.py`, `exceptions.py`) | Accepted |
| T7-D2 | `list_by_client_and_user_id` | `list_by_client_id_and_user_id` | Cosmetic naming; identical signature semantics | Accepted |
| T7-D3 | `list_overlapping(user_id, starts_at, ends_at, exclude_appointment_id)` | `find_overlapping(user_id, date_time, duration_minutes, ...)` | Consistent with TSK-006 D1 window model; overlap semantics identical, ready for TSK-009 | Accepted |
| T7-D4 | No `delete_by_id_and_user_id` | Port includes delete | No delete use-case in MUST scope; add with its own RED cycle when required | Accepted, deferred |
| T7-D5 | No `save_session_notes` / `find_notes_by_appointment_id_and_user_id` | Port includes notes methods | Notes are created via the `Appointment.attach_notes()` factory (TSK-006 D4) and persist with the aggregate; separate notes persistence decided at TSK-010/014 | Accepted, deferred |
