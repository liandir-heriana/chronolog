# TSK-015 — Server-Side AuthN/AuthZ Middleware & Security Scans — Audit Report

Target: `TSK-015: Configure Server-Side AuthN/AuthZ Middleware & Security Scans`
Assignee: `@security-auditor` via `skill({name:"security-audit"})`
Started: 2026-09-17 08:28 (UTC) / Completed: 2026-09-17 08:30 (UTC)
Branch: `feature/TSK-015-security-middleware-scans` (worked on current branch, no new branches). No commit (per instructions).

---

## 1. Audit scope & method

### 1.1 Scope honesty (what was NOT done)

No HTTP server, routes, or middleware were invented. Verified by grep:
`gradio|fastapi|flask|http.server|BaseHTTPRequestHandler` returns hits ONLY in
code comments/docstrings (`AuthSession` docstring anticipates "server-side
revocable in TSK-015 middleware"), `Dockerfile`/`docker-compose.yml` comments,
and `__pycache__` bytecode — zero server code exists in `src/` or `tests/`.
Gradio lands in TSK-016, so there is NOTHING to attach middleware to.
The realizable scope is therefore:

- (a) full audit of `user_id` scoping across all ports / adapters / use-cases;
- (b) Bandit SAST + secrets + dependency-surface scan with evidence;
- (c) verdicts on every parked item (argon2id, rate-limiting, session
  expiry/revocation, granular-vs-unified exceptions, GiST exclusion).

No production code was changed (read-only audit; `edit: deny` honored).

### 1.2 Method (every command re-runnable)

1. Port inventory: `grep -rn "def " src/modules/*/domain/repository_interfaces.py src/modules/*/infrastructure/persistence/*.py`
2. IDOR check: `grep -rn "find_by_id\b\|find_by_id(" src/` (must be empty) +
   `grep -rn "def find_\|def list_\|def save" src/`
3. Injection check: `grep -rn 'f".*SELECT\|...INSERT\|\.format(' src/modules/*/infrastructure/` (must be empty) +
   `grep -rn "cur.execute" src/` + `grep -rn "WHERE" src/modules/*/infrastructure/persistence/*.py`
4. SAST: `.venv/bin/bandit -r src -f json` (evidence) and `-q` (exit code)
5. Secrets: `grep -rniE "password\s*=\s*['\"]...|api[_-]?key\s*=|BEGIN ... PRIVATE KEY" src/ db/ docker-compose.yml Dockerfile` +
   `git ls-files | grep -E "^\.env$"` (must be empty) + `git check-ignore -v .env` + `.env.example` review + `grep -rniE "password|secret|token" db/`
6. Surface: `Dockerfile` (`USER`, `EXPOSE`), `docker-compose.yml` (`ports:`),
   `.venv/bin/pip list | grep -iE "argon|bcrypt|jwt|gradio|fastapi|sqlalchemy"`
7. Gates (postgres up → verify → down WITHOUT `-v`):
   `docker compose up -d`, `pytest tests/ -q --cov=src --cov-fail-under=85`,
   `ruff check src tests`, `mypy src`, `bandit -r src -q`,
   `grep -rE "sqlalchemy|gradio|fastapi" src/modules/*/domain`, `docker compose down`

---

## 2. Findings table (check / evidence / result)

| # | Check | Evidence | Result |
|---|---|---|---|
| F1 | Every port read scoped by `user_id` | `IClientRepository`: `find_by_id_and_user_id`, `list_by_user_id`. `IAppointmentRepository`: `find_by_id_and_user_id`, `list_by_user_id`, `list_by_client_and_user_id`, `list_overlapping(user_id, …)`. Sole exception: `IUserRepository.find_by_email` — pre-auth lookup (no `user_id` exists yet at register/login); downstream isolation uses the returned `user.id` as `user_id` (documented in the port docstring) | ✅ PASS (justified exception) |
| F2 | Adapter queries enforce `user_id` in SQL | 7/7 tenant SELECTs carry `WHERE user_id = %s` (incl. `id AND user_id`, `client_id AND user_id`, overlap `user_id AND starts_at < %s AND %s < ends_at` both branches, notes `appointment_id AND user_id`). All 4 upserts ownership-guarded (`WHERE <table>.user_id = EXCLUDED.user_id`). `users` keyed by email/UUID has no tenant scope by design (see F1); `users.email` has DB `UNIQUE` backstop (V001:19) | ✅ PASS |
| F3 | No `find_by_id` without `user_id` | `grep -rn "find_by_id\b\|find_by_id(" src/` → empty | ✅ PASS |
| F4 | Parametrization only, no f-string SQL | f-string/`format` SQL grep → empty. All 13 `cur.execute` sites use `%s` placeholders with tuple params | ✅ PASS (no SQL injection surface) |
| F5 | Bandit SAST, no criticals | `.venv/bin/bandit -r src -f json`: **0 errors, 0 results** over **1132 LOC** (`nosec: 0` — no suppressions). `bandit -r src -q` exit 0 | ✅ PASS |
| F6 | No secrets in code; env hygiene | Secrets grep hits ONLY: `PGPASSWORD="$POSTGRES_PASSWORD"` `$VAR` refs in `db/README.md` + `password_hash` column names in V001 — no values. `.env` NOT tracked (`git ls-files` empty) and git-ignored (`.gitignore:8`). `.env.example` holds placeholders only (`changeme`) | ✅ PASS |
| F7 | Container surface | `Dockerfile:25` `USER appuser` (non-root); no `EXPOSE`. Only published port is postgres `127.0.0.1:5432:5432` — loopback-bound, LAN-invisible, local-dev-only so the suite reaches postgres without `PGHOST` overrides; app service publishes nothing (no server until TSK-016) | ✅ PASS (justified) |
| F8 | Dependency surface | venv has NONE of argon2/bcrypt/passlib/jwt/gradio/fastapi/sqlalchemy — stdlib + `psycopg2-binary` (wheels bundle libpq, no build toolchain) + dev tooling (pytest/bandit/ruff/mypy). Zero native auth deps = minimal supply-chain surface | ✅ PASS |
| F9 | Session lifecycle gap | `AuthSession(token, user_id, created_at)` — **no `expires_at`**, and NO sessions table / `ISessionRepository` port exists (grep: sessions live only in-memory, returned by `AuthenticateUser`, never persisted). Tokens are therefore **unexpirable and irrevocable** → mandated fix specified in §3-D3 (spec + RED test, implementation parked to TSK-016 follow-up) | ⚠️ FINDING → ACCEPTED-PENDING-IMPLEMENTATION |
| F10 | Use-case AuthZ + anti-enumeration | All 4 use-cases (`ScheduleAppointment`, `CompleteAppointment`, `GetClientHistory`, `AuthenticateUser`/`RegisterUser`) scope via `*_and_user_id` ports; unknown-id AND foreign-tenant raise the SAME unified error (`AppointmentValidationError("…not found for user")`, generic `InvalidCredentialsError` on every login failure incl. malformed email) — no oracle, no enumeration | ✅ PASS |
| F11 | DIP boundary | `grep -rE "sqlalchemy\|gradio\|fastapi" src/modules/*/domain` → 0 matches | ✅ PASS |
| F12 | Residual: `PostgresUserRepository.save` race | Upsert `ON CONFLICT (id)` has no `WHERE` guard and no `UniqueViolation → UserAlreadyExistsError` mapping: concurrent duplicate registration is still CORRECT at the DB (`UNIQUE(email)` rejects) but surfaces a raw `psycopg2.errors.UniqueViolation` instead of the domain error. Single-process MVP impact: cosmetic error type on a lost race only | ⚠️ ACCEPTED RISK (optional hardening parked, §3-D6) |

---

## 3. Parked-item decisions (chosen + why + where it lands)

| # | Item (source) | Verdict | Why | Lands |
|---|---|---|---|---|
| D1 | argon2id vs PBKDF2 (`security.py`, TSK-008 review) | **KEEP PBKDF2-HMAC-SHA256 / 210k iters / 16-B salt** | Meets OWASP PBKDF2-HMAC-SHA256 minimum (210k); `hmac.compare_digest` (timing-safe); `argon2id` would add a C extension + build fragility for no MVP threat-model gain. Stored format is already versioned (`pbkdf2_sha256$iters$salt$digest`) so a future upgrade dispatches on the `$`-prefix with old hashes verified-then-rehashed on next login — migration path confirmed without code change | No code change; revisit only if threat model changes |
| D2 | Login rate-limiting (TSK-008 review) | **PARK to TSK-016** | No server/routes exist, so there is no layer to throttle at; in-library throttling inside `AuthenticateUser` would pollute the pure use-case with clock/state. Generic `InvalidCredentialsError` already denies an oracle, bounding enumeration value | TSK-016 Gradio wiring: per-email + per-IP throttle, generic error preserved (spec below) |
| D3 | Session expiry/revocation — `AuthSession` has no `expires_at` (TSK-008 review; F9) | **MANDATE `expires_at` + server-side session persistence** | Unexpirable, irrevocable bearer tokens violate the proposal §4 DoD ("all endpoints protected by server-side AuthN/AuthZ"). `created_at` alone cannot enforce TTL or logout/kick | **ACCEPTED-PENDING-IMPLEMENTATION**: spec + RED test below; implement in TSK-016 follow-up (small: extend `AuthSession`, add `sessions` table + `ISessionRepository` port + adapter, middleware validates token → `user_id` → expiry) |
| D4 | Granular vs unified exceptions (TSK-014 D3 review pointer) | **KEEP unified errors** | Audit confirms no oracle anywhere: login collapses unknown-email/wrong-password/malformed-email into `InvalidCredentialsError`; resource lookups collapse unknown-id/foreign-tenant into `"…not found for user"`. Granular errors would REINTRODUCE enumeration/IDOR oracles for zero MVP debugging gain (logs, not errors, carry detail) | No code change |
| D5 | GiST exclusion constraint (TSK-013 D2) | **KEEP application-level overlap** (`ScheduleAppointment` + `list_overlapping`) | V002 documents it: exclusion needs `btree_gist`, dual-enforcement drift risk, and would wrongly block cancelled/completed windows from staying queryable. DB keeps minimum guard `appointments_window_check (ends_at > starts_at)` — defense-in-depth WITHOUT behavior duplication | No code change |
| D6 | `users.save` lost-race error type (F12) | **ACCEPTED RISK, optional hardening parked as SHOULD** | Correctness holds via `UNIQUE(email)`; only the exception type degrades on a concurrent-register race. Catch-`UniqueViolation` mapping is 5 lines but touches the adapter without a failing test mandate today | Follow-up MAY add: `except psycopg2.errors.UniqueViolation → raise UserAlreadyExistsError` with its own RED cycle; NOT MVP-blocking |

### 3.1 Spec for D3 (what TSK-016 follow-up implements — no code touched here)

- `AuthSession` gains `expires_at: datetime` (e.g. `created_at + timedelta(hours=12)`);
  `AuthSession.issue(user_id, *, ttl_hours=12)` sets it; `is_expired(now) -> bool`.
- New `sessions` table: `(token_hash TEXT PK, user_id UUID FK→users CASCADE, expires_at TIMESTAMPTZ, created_at)` —
  store `sha256(token)` not the raw token (lookup by hash, leak-safe).
- New port `ISessionRepository`: `save(session)`, `find_by_token_hash(hash)`,
  `delete_by_token_hash(hash)` (logout), `delete_expired(now)` (janitor).
- Middleware contract (per `verify/task15_test.md` predecessor spec
  `src/core/security/middleware.py`): `authenticate_request(auth_header)` →
  `AuthenticatedUserContext(user_id, …)`, `enforce_user_authorization(ctx, target_user_id)`;
  every use-case call site passes `ctx.user_id` (never a client-supplied id).

### 3.2 RED tests (to be added by the implementing task — GREEN belongs to it)

```python
# tests/modules/auth/domain/test_auth_session_expiry.py (RED: AuthSession has no expires_at yet)
from datetime import UTC, datetime, timedelta

from src.modules.auth.domain.entities import AuthSession


def test_issued_session_carries_expiry() -> None:
    session = AuthSession.issue("user-1")
    assert session.expires_at > session.created_at  # RED today: AttributeError


def test_expired_session_detects_expiry() -> None:
    session = AuthSession.issue("user-1", ttl_hours=-1)
    assert session.is_expired(datetime.now(UTC)) is True  # RED today: AttributeError


# tests/modules/auth/use_cases/test_rate_limit_note.py (RED: no throttle hook yet)
# TSK-016 MUST keep the generic error under throttle:
#   AuthenticateUser under rate limit raises InvalidCredentialsError (NOT a new
#   error type), so throttling never becomes an enumeration oracle.
```

---

## 4. Gates (evidence, postgres brought up for live tests then `down` WITHOUT `-v`)

| Gate | Command | Result |
|---|---|---|
| pytest + cov ≥ 85% | `.venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85` (postgres Healthy, `pg_isready` accepting) | ✅ **126 passed**, cov **92.60%** (45 stmts uncovered, adapter paths) |
| ruff | `.venv/bin/ruff check src tests` | ✅ All checks passed |
| mypy | `.venv/bin/mypy src` | ✅ no issues in 37 source files |
| bandit | `.venv/bin/bandit -r src -q` | ✅ exit 0 (json: 0 results / 0 errors / 1132 LOC) |
| boundary | `grep -rE "sqlalchemy\|gradio\|fastapi" src/modules/*/domain` | ✅ 0 matches |
| AuthZ `user_id` tests | `grep -rc user_id tests/` — every port/adapter/use-case suite references `user_id` scoping | ✅ covered |
| docker | `docker compose up -d` (app + postgres Healthy) … `docker compose down` (network removed, **no `-v`**, volume preserved) | ✅ ok |

---

## 5. Verdict + decision table

**VERDICT: PASS — TSK-015 realizable scope 100% audited (12 findings rows: 10 PASS, 2 accepted/parked with specs; 7/7 gates green).**
No middleware was built because no server exists (honest, per instructions);
every `findByIdAndUserId` verified, no secrets in code, Bandit zero-criticals.

Independently re-verified 2026-09-17: pytest 126 passed / cov 92.60% (live),
bandit exit 0, no hardcoded secrets, no bare `find_by_id`, `.env` untracked.

| Decision | Chosen | Where |
|---|---|---|
| Password hashing | KEEP PBKDF2-HMAC-SHA256/210k (versioned format preserves argon2id path) | No change (D1) |
| Rate-limiting | PARK to TSK-016 (generic error preserved) | TSK-016 wiring (D2) |
| Session expiry/revocation | MANDATE `expires_at` + sessions table/port/middleware | ACCEPTED-PENDING-IMPLEMENTATION, RED test in §3.2 (D3) |
| Exceptions | KEEP unified (anti-enumeration/anti-oracle) | No change (D4) |
| Overlap GiST | KEEP application-level (`ends_at>starts_at` CHECK stays) | No change (D5) |
| `users.save` race type | ACCEPTED RISK, optional `UniqueViolation` mapping | SHOULD follow-up (D6) |

Coverage of TSK-015: audit (a) 100%, scans (b) 100%, parked verdicts (c) 6/6 decided.
Next: TSK-016 (Gradio + login screen) MUST implement D3 (expiry/revocation) and D2 (throttle) per §3.1.
