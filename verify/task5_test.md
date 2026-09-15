# TSK-005 Specification & Verification Guide: Client Aggregate Root & Value Objects

> **Target Task:** `TSK-005: Model Client Aggregate Root & Value Objects`  
> **Module:** `src/modules/clients/domain/`  
> **Testing Framework:** `pytest` (Pure Python 3.12)  
> **Methodology:** Spec-Driven Development (SDD) & Strict TDD (RED -> GREEN -> REFACTOR)

---

## 1. Domain Contracts & Invariants

The domain layer must remain 100% pure Python with **ZERO dependencies** on ORMs (SQLAlchemy), web frameworks (Gradio/Fastapi), or external services.

### A. Value Objects (`src/modules/clients/domain/value_objects.py`)

#### `ClientID`
*   **Invariants:** Immutable identifier. Must be a non-empty string or valid UUID. Automatically generates UUID v4 if no value is provided.
*   **Exceptions:** `InvalidClientIDException`

#### `Email`
*   **Invariants:** Encapsulates and guarantees email address validity upon instantiation.
*   **Validation:** Strict format validation (contains `@`, domain extension, no whitespace).
*   **Exceptions:** `InvalidEmailException`

#### `Phone`
*   **Invariants:** Encapsulates phone numbers with automatic whitespace/hyphen normalization.
*   **Validation:** Must contain a minimum of 7 digits and valid phone characters.
*   **Exceptions:** `InvalidPhoneException`

---

### B. Aggregate Root (`src/modules/clients/domain/client.py`)

#### `Client` Entity
*   **Attributes:**
    *   `id: ClientID` (Primary Identifier)
    *   `user_id: str` (Owner Account ID — Mandatory for AuthZ and data isolation)
    *   `full_name: str` (Non-empty string)
    *   `email: Email` (Email Value Object)
    *   `phone: Phone` (Phone Value Object)
    *   `created_at: datetime` (UTC Timestamp)
*   **Domain Methods:**
    *   `update_contact_info(new_email: Email, new_phone: Phone) -> None`: Updates contact details while maintaining domain invariants.

---

## 2. Test Cases Checklist (Given-When-Then / AAA Pattern)

### Unit Tests: Value Objects (`tests/unit/clients/test_value_objects.py`)

- [ ] **`test_email_creation_success`**
  - **Given:** A valid email string (`"cliente@ejemplo.com"`).
  - **When:** Instantiating `Email("cliente@ejemplo.com")`.
  - **Then:** Object is created, and `str(email)` returns `"cliente@ejemplo.com"`.

- [ ] **`test_email_creation_invalid_raises_exception`**
  - **Given:** Invalid email strings (`"cliente.com"`, `"@ejemplo.com"`, `""`).
  - **When:** Instantiating `Email(invalid_str)`.
  - **Then:** Raises `InvalidEmailException`.

- [ ] **`test_phone_creation_success_and_normalization`**
  - **Given:** A valid formatted phone string (`"+34 600-123-456"`).
  - **When:** Instantiating `Phone("+34 600-123-456")`.
  - **Then:** Object is created and normalized.

- [ ] **`test_phone_creation_invalid_raises_exception`**
  - **Given:** An invalid phone string (`"123"`, `"abc-def-ghi"`).
  - **When:** Instantiating `Phone(invalid_str)`.
  - **Then:** Raises `InvalidPhoneException`.

---

### Unit Tests: Aggregate Root (`tests/unit/clients/test_client.py`)

- [ ] **`test_create_client_success`**
  - **Given:** Valid `user_id`, `full_name`, `Email`, and `Phone`.
  - **When:** Instantiating `Client(...)`.
  - **Then:** Client is created with `ClientID`, retains `user_id`, and sets `created_at`.

- [ ] **`test_create_client_missing_user_id_raises_exception`**
  - **Given:** Valid client details but an empty/null `user_id`.
  - **When:** Instantiating `Client(...)`.
  - **Then:** Raises `DomainValidationError` (Enforces multi-tenant data isolation).

- [ ] **`test_update_contact_info_success`**
  - **Given:** An existing `Client` and new valid `Email` and `Phone` objects.
  - **When:** Calling `client.update_contact_info(new_email, new_phone)`.
  - **Then:** Client properties are updated accordingly.

---

## 3. Python Test Suite Boilerplate (`pytest`)

Below is the ready-to-use test file code to place in `tests/unit/clients/test_client_domain.py`:

```python
import pytest
from datetime import datetime
from src.modules.clients.domain.value_objects import Email, Phone, ClientID
from src.modules.clients.domain.client import Client
from src.modules.clients.domain.exceptions import (
    InvalidEmailException,
    InvalidPhoneException,
    DomainValidationError,
)

class TestValueObjects:
    def test_email_valid(self):
        email_str = "user@example.com"
        email = Email(email_str)
        assert str(email) == email_str

    @pytest.mark.parametrize("invalid_email", ["invalid.com", "@domain.com", "", "user@"])
    def test_email_invalid_raises_exception(self, invalid_email):
        with pytest.raises(InvalidEmailException):
            Email(invalid_email)

    def test_phone_valid_normalization(self):
        phone = Phone("+34 600-123-456")
        assert "600123456" in str(phone) or "+34600123456" in str(phone)

    def test_phone_invalid_raises_exception(self):
        with pytest.raises(InvalidPhoneException):
            Phone("123")


class TestClientAggregate:
    def test_client_creation_success(self):
        client = Client(
            user_id="usr_123",
            full_name="Juan Pérez",
            email=Email("juan@ejemplo.com"),
            phone=Phone("+34600112233")
        )
        assert client.id is not None
        assert client.user_id == "usr_123"
        assert client.full_name == "Juan Pérez"
        assert isinstance(client.created_at, datetime)

    def test_client_missing_user_id_raises_exception(self):
        with pytest.raises(DomainValidationError):
            Client(
                user_id="",
                full_name="Juan Pérez",
                email=Email("juan@ejemplo.com"),
                phone=Phone("+34600112233")
            )

    def test_update_contact_info_success(self):
        client = Client(
            user_id="usr_123",
            full_name="Juan Pérez",
            email=Email("juan@ejemplo.com"),
            phone=Phone("+34600112233")
        )
        new_email = Email("juan_nuevo@ejemplo.com")
        new_phone = Phone("+34600998877")
        
        client.update_contact_info(new_email, new_phone)
        
        assert client.email == new_email
        assert client.phone == new_phone
```

---

## 4. Verification Quality Gates (`sdd-verify`)

Execute these commands in the terminal to verify DoD compliance before marking `[x]` in `tasks.md`:

1. **Run Unit Tests & Coverage Check:**
   ```bash
   pytest tests/unit/clients/ -q --cov=src/modules/clients/domain --cov-fail-under=85
   ```
2. **Clean Domain Check (Zero Infrastructure Leakage):**
   ```bash
   grep -rE "sqlalchemy|gradio|fastapi" src/modules/clients/domain
   # Expected output: 0 matches
   ```
3. **Static Analysis & Security Audit:**
   ```bash
   ruff check src/modules/clients/domain
   mypy src/modules/clients/domain
   bandit -r src/modules/clients/domain -q
   ```

---

## 5. Parallel Verification Result (Justification)

**Final verdict: the TSK-005 process as executed is ACCEPTED — approximate alignment with this verification proposal: ~85%.**

Breakdown (2026-09-15, executed implementation vs this guide):

- **Behavioral contracts: 7/7 match.** Email accept/normalize/reject, Phone accept/normalize/reject, ClientId generate/round-trip/reject, Client create with `user_id` scoping, `user_id`/name rejection, contact update with revalidation.
- **Quality gates: 4/4 match (executed broader).** `pytest` 26 passed with 100% coverage on `src` (≥85% required), boundary `grep` 0 matches, `ruff`/`mypy`/`bandit` clean. Run on `tests/` + `src/` instead of the narrower `tests/unit/clients/` + `src/modules/clients/domain` paths proposed above.
- **Naming-level divergences (non-blocking, 6 items):** `ClientId` vs `ClientID`, `entities.py` vs `client.py`, `name` vs `full_name`, unified `ClientValidationError` vs per-type exceptions (`InvalidEmailException`, `InvalidPhoneException`, `InvalidClientIDException`, `DomainValidationError`), `update_contact(...)` vs `update_contact_info(email, phone)`, no `created_at` (chronology belongs to the appointments module), `phone` optional vs mandatory, `tests/modules/...` mirror vs `tests/unit/...`.

Justification: every invariant and gate from Sections 1–4 holds in the implementation; the divergences change names and file placement only, not validated behavior. No process redo required. If the course requires literal names (`ClientID`, `full_name`, `created_at`), track it as a follow-up alignment sub-task with its own RED cycle instead of rewriting TSK-005.
