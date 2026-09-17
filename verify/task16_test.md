# TSK-016 — Web UI Interface & Login Screen (Gradio) + D3/D2 Security Debt — Verification Report

Target: `TSK-016: Set Up Web UI Interface & Login Screen (Gradio)`
Assignee: `@frontend-dev` via `skill({name:"ui-integration"})`
Started: 2026-09-17 09:54 (UTC) / Completed: 2026-09-17 10:15 (UTC)
Branch: `feature/TSK-016-gradio-ui` (worked on current branch, no new branches). No commit (per instructions).
Gradio: `6.27.0` (installed via `.venv/bin/python -m pip install gradio`; added to `Dockerfile` pip line).

> Note: a stub `verify/task16_test.md` existed from planning (template with
> non-existent API: `session_id`, `AuthenticateUserUseCase`,
> `SessionExpiredError`/`RateLimitExceededError`/`UnauthenticatedError`,
> 24h TTL, `src/presentation/ui/`). It is SUPERSEDED by this report:
> distinct error types were REJECTED per TSK-015 D2/D4 (generic
> `InvalidCredentialsError`, no oracle); TTL is 12h per §3.1 spec; actual
> paths are `src/presentation/app.py`, `src/composition.py`, `src/main.py`,
> `src/core/security/`. Deviations are listed in §5.

---

## 1. What was built

### 1.1 Mandatory security debt (TSK-015 §3.1 + §3.2, GREEN targets met)

**D3 — expiring, revocable, server-side sessions:**
- `AuthSession` gains `expires_at: datetime` (`created_at + ttl`, default
  12h via `DEFAULT_SESSION_TTL_HOURS`); `issue(user_id, *, ttl_hours=12)`;
  `is_expired(now) -> bool` (boundary inclusive: `now >= expires_at`;
  naive datetimes rejected). File: `src/modules/auth/domain/entities.py`.
- `hash_token()` (`sha256` hex) in `src/modules/auth/domain/security.py` —
  the DB stores only the hash, never the raw bearer token.
- Port `ISessionRepository` (`save`, `find_by_token_hash`,
  `delete_by_token_hash` logout, `delete_expired(now) -> int` janitor) in
  `src/modules/auth/domain/repository_interfaces.py`.
- Migration `db/migrations/V003__sessions.sql` (`token_hash TEXT PK CHECK
  64 chars`, `user_id UUID FK→users CASCADE`, `expires_at`, `created_at`,
  indexes on `user_id`/`expires_at`; idempotent).
- Adapter `PostgresSessionRepository` (`src/modules/auth/infrastructure/
  persistence/postgres_session_repository.py`, `%s`-only SQL, `DATABASE_URL`
  via stdlib `os`).
- Middleware `src/core/security/middleware.py`: `authenticate_request(
  auth_header)` → `AuthenticatedUserContext(user_id, token_hash,
  expires_at)` (accepts `Bearer <t>` or raw; unknown/missing/malformed/
  expired → generic `InvalidCredentialsError`; expired rows best-effort
  purged); `enforce_user_authorization(ctx, target)` → `AuthorizationError
  (ValueError)` on cross-user target. Every UI handler calls both and
  passes `ctx.user_id` (never a client-supplied id) into use-cases.

**D2 — login throttle preserving the generic error:**
- `LoginRateLimiter` (`src/core/security/rate_limit.py`, stdlib only,
  sliding-window in-memory, `max_attempts=5`/`window_seconds=300`
  configurable): `check` raises generic `InvalidCredentialsError` when
  throttled; `record_failure`/`record_success` (success clears). Lives
  OUTSIDE `AuthenticateUser` (pure use-case stays clock/state-free per D2
  verdict). `handle_login` enforces per-email AND per-IP (two keys
  `email:<lower>` + `ip:<addr>`, failures recorded on both).

### 1.2 Gradio dashboard + composition root

- `src/presentation/app.py` (Gradio ONLY here): auth row (Login/Register/
  Logout, token in `gr.State`) + tabs **Clients** (register/list),
  **Scheduler** (schedule/list), **History** (client history + notes review,
  complete-with-notes). Pure testable handlers (`handle_register`,
  `handle_login`, `handle_logout`, `handle_create_client`,
  `handle_list_clients`, `handle_schedule`, `handle_list_appointments`,
  `handle_history`, `handle_complete`) + thin `build_demo(deps)` wiring.
  No SQL/validation logic; no adapter imports (proven by grep).
- `src/composition.py`: `resolve_dsn` / `migrations_dir` /
  `ensure_schema` (applies V001+V002+V003 idempotently on every boot) /
  `build_context` (Postgres adapters → use-cases + limiter). Only place
  (with `src/main.py`) allowed to touch concrete adapters.
- `src/main.py`: `ensure_schema()` then serve `0.0.0.0:7860`.
- `src/modules/clients/use_cases/register_client.py`: NEW `RegisterClient`
  (MUST Client Registration had no use-case; Clients tab needs a boundary
  so the UI never builds rows or touches adapters). RED-first, see §3.
- `Dockerfile`: pip line gains `gradio`; `COPY db/`; CMD
  `["python", "-m", "src.main"]`. `docker-compose.yml`: app publishes
  `127.0.0.1:7860:7860` (loopback, LAN-invisible — consistent with the
  TSK-015 F7 postgres decision) + `GRADIO_PORT`.
- T10-D1 bridge (ONE place, documented in `handle_complete`): the
  `CompleteAppointment` port is frozen, so notes content persists via the
  adapter-local `save_with_notes`/`find_notes_by_appointment_and_user_id`
  through duck-typing (`getattr`, no adapter import); fakes without those
  methods still hold status via the port save.

---

## 2. Checklist

- [x] TSK-016 marked In Progress with UTC timestamp; dashboard updated.
- [x] RED first: 5 expiry failures + 4 collection errors (recorded §3).
- [x] GREEN: D3 (entity/hash/port/V003/adapter/middleware), D2 (limiter),
  `RegisterClient`, composition, presentation, `main`, Dockerfile/compose.
- [x] Gradio installed `6.27.0` (honest; no faking).
- [x] UI calls use-cases with `ctx.user_id` on every action; expired token
  rejected; logout revokes; throttle keeps the generic error.
- [x] Full gates: pytest live 181 passed + cov 90.64% (≥85), ruff/mypy
  clean, bandit 0 high/critical (exit 1 on 1 medium + 1 low, both accepted), boundary domain+use-cases 0,
  gradio only in presentation, compose config + `up --build` + curl 200 +
  10-step live smoke green + `down` clean (no `-v`).
- [x] README `Run the stack` updated (serves on `:7860`).
- [x] TSK-016 `[x]` + timestamp + dashboard + Notes; this report.

---

## 3. Live evidence (incl. RED proof)

RED (before production code):

```text
.venv/bin/python -m pytest tests/modules/auth/domain/test_auth_session_expiry.py -q
5 failed in 0.09s
E TypeError: AuthSession.issue() got an unexpected keyword argument 'ttl_hours'
E AttributeError (expires_at / is_expired)

.venv/bin/python -m pytest <4 new suites> -q
4 errors in 0.42s
E ModuleNotFoundError: No module named 'src.core.security.rate_limit' (test_rate_limit)
E ModuleNotFoundError: No module named 'src.core.security.middleware' (test_middleware)
E ImportError: cannot import name 'hash_token' (test_postgres_session)
E ModuleNotFoundError: No module named 'src.modules.clients.use_cases' (test_register_client)
```

GREEN (unit, no DB): `164 passed, 17 skipped`.

Full suite (postgres Healthy, loopback, V001+V002+V003):

```text
.venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85
src/presentation/app.py  239 stmts, 17 miss → 93%
TOTAL  1079 stmts, 101 miss → 90.64%
Required test coverage of 85% reached. Total coverage: 90.64%
181 passed in 8.40s   (164 + 17 live: 12 adapters + 5 sessions, 0 skipped)
```

Docker + smoke:

```text
docker compose config            # valid (DATABASE_URL interpolates, 127.0.0.1:7860)
docker compose up --build -d     # app Up (python -m src.main), postgres Healthy
docker logs chronolog-app        # * Running on local URL: http://0.0.0.0:7860
curl localhost:7860/             # HTTP 200
curl localhost:7860/config       # {"version":"6.27.0","mode":"blocks",
                                 #  "# ChronoLog — Appointment & Session Management (MVP)"...}
ss -ltn                          # 127.0.0.1:7860 + 127.0.0.1:5432 (loopback only)
PYTHONPATH=. .venv/bin/python /tmp/opencode/smoke16.py   # live postgres via UI handlers:
  1 register: Registered smoke16@example.com. Please log in.
  2 login ok, user: 196f669a-…
  3 middleware resolves token -> 196f669a-…
  4 sessions row is sha256 hash, leak-safe
  5 client: ca0c351d-… / 6 scheduled: 435cbc24-…
  7 complete + notes persisted: Smoke notes ok.
  8 expired token rejected with generic error
  9 logout revokes session
  10 throttle blocks with generic error
  SMOKE16 ALL GREEN
docker compose down              # network removed, no -v, volume kept; no leftovers
```

No secrets logged: DSNs/passwords never printed; `.env` untracked+ignored.

---

## 4. Gates

| Gate | Command | Result |
|---|---|---|
| pytest + cov ≥ 85% | `pytest tests/ -q --cov=src --cov-fail-under=85` (live) | ✅ 181 passed, 90.64% |
| ruff | `ruff check src tests` | ✅ All checks passed |
| mypy | `mypy src` | ✅ no issues in 48 source files |
| bandit | `bandit -r src -q` (exit 1: 1 medium + 1 low, 0 high/critical) | ✅ 0 high/critical (2 noted non-criticals: B104 bind-all — required inside containers, LAN gated at compose loopback; B106 `token=""` placeholder — false positive, raw token never stored) |
| boundary domain+use-cases | `grep -rE "sqlalchemy\|gradio\|fastapi" src/modules/*/domain src/modules/*/use_cases` | ✅ 0 matches |
| gradio scope | `grep -rln gradio src/` | ✅ only `src/presentation/app.py` |
| no adapter imports in UI | `grep -rnE "^(import\|from).*Postgres\|psycopg2\|sqlalchemy" src/presentation/ src/main.py src/core/` | ✅ 0 (composition owns `psycopg2` by design) |
| AuthZ `user_id` | every handler resolves `ctx` + passes `ctx.user_id`; ports/adapters `WHERE user_id` (TSK-015 F1/F2 hold); tests reference `user_id` throughout | ✅ covered |
| docker | `config` → `up --build -d` → curl 200 → smoke 10/10 → `down` (no `-v`) | ✅ ok |

---

## 5. Verdict + %

**VERDICT: PASS — TSK-016 100% delivered (dashboard + D3 + D2) with all DoD gates green.**

- New tests: 55 (5 expiry + 5 limiter + 8 middleware + 5 session-live + 9 register-client + 14 presentation + 5 composition + 4 pre-existing-skipped-now-live). Full: 181/181 passed (100%).
- Coverage: 90.64% total (≥85 gate); presentation 93%, new use-cases/ports 100%/86%+.
- TSK-016 ready for `[x]` closure. Next: TSK-017 (deep wiring polish on top of this dashboard).

### Decision table

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Session TTL | No expiry (status quo) vs 12h vs 24h (stub) | 12h default, `ttl_hours` param | TSK-015 §3.1 spec (`created_at + 12h`); unexpirable tokens were the top finding |
| Token storage | Raw token column vs `sha256` hash PK | `token_hash TEXT PK` (64-char CHECK) | DB leak alone cannot impersonate; lookup hashes the presented token |
| Throttle error | New `RateLimitExceededError` (stub) vs generic | Generic `InvalidCredentialsError` | D2/D4: distinct errors become enumeration oracles; throttle must be invisible |
| Throttle placement | Inside `AuthenticateUser` vs wiring layer | `LoginRateLimiter` in `core/security`, checked in `handle_login` | D2 verdict: keeps the pure use-case clock/state-free; per-email AND per-IP keys |
| Middleware errors | `SessionExpiredError`/`UnauthenticatedError` (stub) vs generic | Generic `InvalidCredentialsError` for all token failures | No oracle (missing/unknown/expired indistinguishable); `AuthorizationError` only for the programming-error guard `enforce_*` |
| App publish | All-interfaces `7860:7860` vs loopback | `127.0.0.1:7860:7860` | Local-dev-only, consistent with postgres loopback (F7); container still binds `0.0.0.0` internally (required) → B104 accepted |
| Notes persistence | New port methods vs adapter-local bridge | Duck-typed `save_with_notes` in `handle_complete` only | Port frozen per T10-D1; single documented bridge, no adapter imports in UI |
| Missing client use-case | UI builds `Client` directly vs new use-case | NEW `RegisterClient` (RED-first) | MUST Client Registration had no boundary; UI must not construct rows or touch adapters |
| Bandit B104/B106 | `nosec` suppress vs accept+document | Accept + document (0 high/critical) | Honest: bind-all is required in-container; `token=""` is a rehydration placeholder, not a credential |
| Stub deviations | Follow stale stub vs TSK-015 spec | Follow `verify/task15_test.md` §3.1/§3.2 | Stub contradicts D2/D4 anti-oracle mandates and names non-existent modules; spec is authoritative |
