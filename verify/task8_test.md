# TSK-008: User Authentication & Registration Use Case

**Target / Task:** `TSK-008: Implement 'User Authentication & Registration' Use Case`
**Module:** `src/modules/auth/domain/` + `src/modules/auth/use_cases/`
**Assigned to:** `@backend-dev`
**SDD Route:** `skill({name:"sdd-apply"})` via `/apply TSK-008`

---

## 1. Domain Contracts & Invariants

The auth layer is **100% pure Python (`stdlib` only)**: zero imports of
`sqlalchemy`, `gradio`, `fastapi` in `domain/` **and** `use-cases/`.
Use-cases depend exclusively on the `IUserRepository` port (DIP).

### A. Value Objects (`src/modules/auth/domain/value_objects.py`)

#### `UserId`
*   **Invariants:** Immutable UUID identifier. `generate()` creates a new random id;
    construction from string normalizes via `UUID(...)`.
*   **Exceptions:** `UserValidationError` on non-UUID input.
*   **Role:** A `User.id` **is** the AuthZ `user_id` scoping every read in the
    clients/appointments ports (IDOR prevention downstream).

#### `UserEmail`
*   **Invariants:** Auth-owned email VO (mirrors the clients `Email` pattern but
    lives in `auth` so the module has no cross-module domain dependency).
    Normalized to `strip().lower()`; max 254 chars; strict `user@domain.tld` shape.
*   **Exceptions:** `UserValidationError` on invalid input.

### B. Aggregate Root & Session (`src/modules/auth/domain/entities.py`)

#### `User` Entity
*   **Attributes:** `id: UserId`, `email: UserEmail`, `password_hash: str`.
*   **Invariants:** `password_hash` must be non-empty; **plaintext never reaches
    this entity** — hashing happens in `security.hash_password()` before
    construction, enforced by the `RegisterUser` flow and covered by test
    (stored hash `!=` password and does not contain it).

#### `AuthSession` (frozen value object)
*   **Attributes:** `token: str` (opaque), `user_id: str`, `created_at: datetime` (UTC).
*   **Factory:** `AuthSession.issue(user_id)` validates non-empty `user_id` and
    mints a fresh `secrets.token_urlsafe(32)` token — unique per login, carrying
    no identity data (no JWT, no claims to leak).

### C. Security primitives (`src/modules/auth/domain/security.py`)
*   `hash_password(password) -> str`: PBKDF2-HMAC-SHA256, 210 000 iterations,
    16-byte `secrets` salt; format `pbkdf2_sha256$iter$salt_hex$hash_hex`.
    Rejects passwords < 8 chars or blank with `UserValidationError`.
*   `verify_password(password, hash) -> bool`: `hmac.compare_digest`; malformed
    stored hashes safely return `False` (never crash or bypass login).

### D. Port (`src/modules/auth/domain/repository_interfaces.py`)
*   `IUserRepository`: `save(user)`, `find_by_email(email) -> User | None`.
*   Reads are keyed by **email, not `user_id`**, because registration/login run
    *before* a `user_id` exists (documented anti-enumeration + lifecycle decision).

### E. Use cases (`src/modules/auth/use_cases/`)
*   `RegisterUser(users).execute(*, email, password) -> User`: normalize/validate
    email → reject duplicates (`UserAlreadyExistsError`, case-insensitive via
    normalized lookup) → hash → `UserId.generate()` → `save` → return.
*   `AuthenticateUser(users).execute(*, email, password) -> AuthSession`: normalize
    email (**malformed/unknown/wrong all raise the same generic
    `InvalidCredentialsError("Invalid email or password")`** — no user
    enumeration) → `verify_password` → `AuthSession.issue(str(user.id))`.

---

## 2. Test Checklist (Given-When-Then / AAA)

### Domain (`tests/modules/auth/domain/test_user.py`)
- [ ] **email accept + normalize** — Given `"  Pro@Example.COM "` → `value == "pro@example.com"`.
- [ ] **email reject** — Given `""`, `"no-at-sign"`, `"a@b"`, over-long, with-space → `UserValidationError`.
- [ ] **userid generate/round-trip/reject** — `generate()` unique; `UserId(str(uid)) == uid`; `"not-a-uuid"` raises.
- [ ] **hash never plaintext** — hash `!=` password and does not contain it.
- [ ] **hash uses random salt** — same password hashes twice → different strings.
- [ ] **verify accept/reject** — correct → `True`; wrong → `False`.
- [ ] **weak password rejected** — `""`, `"   "`, `"short"`, `"1234567"` → `UserValidationError`.
- [ ] **user stores hash** — entity verifies against the original password.
- [ ] **tokens opaque + unique** — two `issue()` calls → distinct tokens, none embedding `user_id`.
- [ ] **session rejects empty user_id**.

### Use cases (`tests/modules/auth/use_cases/test_auth.py`, in-memory `IUserRepository` fake)
- [ ] **register success** — normalized email persisted, hash ≠ plaintext, round-trip via `find_by_email`.
- [ ] **register duplicate** — same email, different case → `UserAlreadyExistsError`.
- [ ] **register invalid email / weak password** → `UserValidationError`.
- [ ] **ids unique per registration** — two users → distinct `UserId`.
- [ ] **login success** — returns session with `user_id == str(owner.id)`, non-empty token; email case-insensitive.
- [ ] **wrong password / unknown email / malformed email** — all raise
    `InvalidCredentialsError` with the **identical** `GENERIC_MESSAGE`.
- [ ] **token unique per login** — two logins → different tokens.

---

## 3. Executable Test Reference (pointer, not a duplicate)

Full boilerplate lives in the repo — this guide does not duplicate it:
*   `tests/modules/auth/domain/test_user.py` — VO, hashing, entity, session tests.
*   `tests/modules/auth/use_cases/test_auth.py` — use-case tests with the
    `InMemoryUserRepository(IUserRepository)` fake (`dict` keyed by normalized email):

```python
class InMemoryUserRepository(IUserRepository):
    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}

    def save(self, user: User) -> None:
        self._by_email[user.email.value] = user

    def find_by_email(self, email: UserEmail) -> User | None:
        return self._by_email.get(email.value)
```

RED proof (pre-implementation): both test modules failed collection with
`ModuleNotFoundError: No module named 'src.modules.auth'`.

---

## 4. Quality Gates

Before marking `[x]` in `doc/tasks.md`:
1. **Tests + coverage:** `pytest tests/ -q --cov=src --cov-fail-under=85`
2. **Domain/use-case purity:** `grep -rE "sqlalchemy|gradio|fastapi" src/modules/*/domain src/modules/auth/use_cases` (0 matches)
3. **Lint/types/scan:** `ruff check src tests` + `mypy src` + `bandit -r src -q`
4. **Docker:** N/A — no infrastructure in this task (deferred to TSK-012/014).

---

## 5. Parallel Verification Result (Justification)

**Final verdict: the executed TSK-008 process is ACCEPTED — alignment with this verification proposal: ~100%.**

Breakdown (2026-09-16, executed implementation vs this guide):

- **Contracts: 8/8 hold.** Auth-owned `UserEmail`/`UserId`, `User` hash-only storage,
    PBKDF2-HMAC-SHA256 + random salt, opaque unique-per-login tokens, `IUserRepository`
    (`save`/`find_by_email`), `RegisterUser` (validate → dedupe → hash), `AuthenticateUser`
    (verify → session, generic error on all failure modes incl. malformed email).
- **Checklist: 17/17 equivalent.** 38 new test cases (25 test functions) across the two
    files in Section 3; RED confirmed via collection-time `ModuleNotFoundError`.
- **Quality gates: 4/4 equivalent.** `pytest` 89 passed (51 prior + 38 new), total cov
    94.84% (auth module alone ~94–96%; both use-cases 100%), `ruff`/`mypy`/`bandit` clean,
    boundary `grep` 0 matches, Docker N/A as declared in Section 4.
    Independently re-verified 2026-09-16: 89 passed, 38/38 auth tests, total cov 94.84%.

### Modeling Decision Log (TSK-008, 2026-09-16)

| # | Adopted decision | Spec alternative (§1) | Rationale | Status |
|---|---|---|---|---|
| T8-D1 | PBKDF2-HMAC-SHA256 (stdlib, 210k iters, 16-B salt) | bcrypt/Argon2 per TSK-008 title | Neither installed in `.venv`; native deps out of scope — zero-dependency, OWASP-listed; revisit in TSK-015 audit | Accepted |
| T8-D2 | Opaque `secrets.token_urlsafe(32)` session | JWT | Zero deps, server-revocable in TSK-015, no claim leakage; JWT only if stateless need appears | Accepted |
| T8-D3 | `use_cases/` (underscore) package | `use-cases/` per AGENTS.md layout | Hyphen not Python-importable; same hexagonal role, rename is mechanical | Accepted |
| T8-D4 | `IUserRepository.find_by_email` unscoped by `user_id` | Every read scoped by `user_id` | Auth runs pre-`user_id`; created `User.id` becomes the scoping id downstream | Accepted |
| T8-D5 | Generic `InvalidCredentialsError` incl. malformed email | Field-level email error on login | Any distinction enables enumeration; one message for all failures | Accepted |
| T8-D6 | Min password length 8 enforced in `hash_password` | Email-only validation in task brief | Single choke point, standard baseline; documented here, covered by test | Accepted |
| T8-D7 | Auth-owned `UserEmail` copy (not shared) | Reuse clients `Email` | Keeps `auth` free of cross-module domain imports (module autonomy) | Accepted |
