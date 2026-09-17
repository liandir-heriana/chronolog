# TSK-014 — Postgres Database Repositories (Adapters) — Verification Report

Target: `TSK-014: Implement Postgres Database Repositories (Adapters)`
Assignee: `@backend-dev` via `skill({name:"sdd-apply"})`
Started: 2026-09-17 07:33 (UTC) / Completed: 2026-09-17 07:39 (UTC)
Branch: `main` (no new branches per task instructions). No commit (per instructions).

---

## 1. Adapter map

All adapters live in `src/modules/*/infrastructure/persistence/` and depend
ONLY on domain ports/entities plus stdlib `os` (`DATABASE_URL`) and `psycopg2`.
Zero ORM/framework imports in `domain/` and `use-cases/` (boundary grep 0).

| Adapter (concrete) | File | Port (domain) | Methods |
|---|---|---|---|
| `PostgresUserRepository` | `src/modules/auth/infrastructure/persistence/postgres_repository.py` | `IUserRepository` | `save(user)` — upsert on `id`; `find_by_email(email)` — exact match |
| `PostgresClientRepository` | `src/modules/clients/infrastructure/persistence/postgres_repository.py` | `IClientRepository` | `save(client)` — upsert ownership-guarded; `find_by_id_and_user_id(client_id, user_id)` — `WHERE id=%s AND user_id=%s`; `list_by_user_id(user_id)` — `WHERE user_id=%s ORDER BY created_at, id` |
| `PostgresAppointmentRepository` | `src/modules/appointments/infrastructure/persistence/postgres_repository.py` | `IAppointmentRepository` | `save(appt)` — upsert ownership-guarded; `find_by_id_and_user_id` — `WHERE id AND user_id`; `list_by_user_id` — `WHERE user_id ORDER BY starts_at`; `list_by_client_and_user_id` — `WHERE client_id AND user_id`; `list_overlapping(user_id, S, E, exclude)` — `WHERE user_id=%s AND starts_at < %s AND %s < ends_at [+ AND id != %s]` (half-open `[S,E)`); adapter-local `save_with_notes(appt, notes)` + `find_notes_by_appointment_and_user_id` (ONE-transaction aggregate, NOT port methods — port stays frozen per T10-D1) |

SQL hygiene (all three adapters):

- Parameterized queries ONLY — `%s` placeholders with param tuples. No f-strings
  in SQL (`grep f-string SQL` = 0; `bandit` B608 clean by construction).
- Every appointment/client read includes `WHERE user_id = %s` (IDOR prevention).
- Upsert re-saves are ownership-guarded:
  `ON CONFLICT (id) DO UPDATE ... WHERE <table>.user_id = EXCLUDED.user_id`,
  so a guessed UUID can never hijack a foreign row (silent no-op instead).
- Connection via `DATABASE_URL` env (stdlib `os`, no config framework):
  `Postgres*(dsn: str | None = None)` uses explicit `dsn` in tests,
  else `os.getenv("DATABASE_URL")` (raises `RuntimeError` if unset).
- Row → entity mapping functions (`_row_to_user/_row_to_client/_row_to_appointment/_row_to_notes`)
  coerce via `str(...)`, validate via domain VOs/constructors, and wrap
  unexpected shapes as the unified domain errors
  (`UserValidationError` / `ClientValidationError` / `AppointmentValidationError`)
  — corrupt rows raise domain errors, never raw crash.

`Dockerfile` change (one line): `pip install ... psycopg2-binary`
(see decision table). `docker compose config` still valid.

---

## 2. Checklist

- [x] TSK-014 marked In Progress with UTC timestamp; dashboard updated.
- [x] RED: 3 live integration test files written FIRST, collection failed
  with `ModuleNotFoundError` (recorded in §3).
- [x] GREEN: `psycopg2-binary` installed into `.venv`; three adapters
  implemented; `Dockerfile` pip line extended.
- [x] Client round-trip + NULL phone + cross-user invisibility + upsert.
- [x] Appointment round-trip + cross-user invisibility on every read.
- [x] Overlap: overlapping seed hits, adjacent window misses,
  `exclude_appointment_id` skips self, other-user window invisible.
- [x] Complete + `attach_notes` aggregate: `COMPLETED` persists,
  notes re-attach on reload, notes row round-trips via ONE-transaction
  `save_with_notes`, notes read is user-scoped (attacker → `None`).
- [x] User round-trip + unknown email → `None` + same-id hash upsert.
- [x] Live integration pattern: `pytest.mark.skipif` on socket/connect failure
  (never fake green); per-test `TRUNCATE ... CASCADE` isolation; migrations
  applied idempotently from `db/migrations/V001+V002` inside fixtures.
- [x] Full gates: pytest + cov ≥85, ruff, mypy, bandit, boundary grep,
  compose config, postgres `up`/`down` (no `-v`).
- [x] TSK-007 review honored: `delete_by_id_and_user_id` NOT added
  (T7-D4 deferred, no use-case requires it); unified
  `AppointmentValidationError`/`ClientValidationError` kept (D3).

---

## 3. Live evidence (incl. RED proof)

RED (before production code, postgres down, adapters absent):

```text
.venv/bin/python -m pytest \
  tests/modules/auth/infrastructure/test_postgres_user.py \
  tests/modules/clients/infrastructure/test_postgres_client.py \
  tests/modules/appointments/infrastructure/test_postgres_appointment.py -q

ERROR tests/modules/auth/infrastructure/test_postgres_user.py
ERROR tests/modules/clients/infrastructure/test_postgres_client.py
ERROR tests/modules/appointments/infrastructure/test_postgres_appointment.py
3 errors in 0.21s
E ModuleNotFoundError: No module named 'src.modules.<...>.infrastructure'
```

Recorded honestly: collection failed on the adapter imports (psycopg2 was also
absent at that point — either failure counts as RED; the adapter import is listed
first in each file so it surfaces first).

Driver install (GREEN prerequisite):

```text
.venv/bin/python -m pip install psycopg2-binary
Successfully installed psycopg2-binary-2.9.13
.venv/bin/python -c "import psycopg2; print(psycopg2.__version__)"
psycopg2 2.9.13 (dt dec pq3 ext lo64)
```

Postgres live (compose has no published ports, so host tests used the bridge IP):

```text
docker compose up -d postgres
chronolog-postgres Up (health: starting) → Up (healthy), 5432/tcp
pg_isready: /var/run/postgresql:5432 - accepting connections
docker inspect → 172.18.0.2; socket 172.18.0.2:5432 reachable
PGHOST=172.18.0.2 .venv/bin/python -m pytest \
  tests/modules/*/infrastructure/test_postgres_*.py -v
12 passed in 2.02s
  - TestPostgresUserRepository: 3 passed (round-trip, unknown→None, upsert)
  - TestPostgresClientRepository: 4 passed (round-trip, NULL phone, IDOR, upsert)
  - TestPostgresAppointment*: 5 passed (round-trip, IDOR, overlap×2, notes aggregate)
```

Full suite (unit + live, same `PGHOST`):

```text
PGHOST=172.18.0.2 .venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85
126 passed in ~3.5s (114 baseline + 12 new)
TOTAL 608 stmts, 45 miss → 92.60% (required 85% reached)
```

Post-fix re-verification (loopback publish, no `PGHOST`, 2026-09-17):

```text
unset PGHOST
docker compose up -d postgres   # now publishes 127.0.0.1:5432
.venv/bin/python -m pytest tests/modules/*/infrastructure/ -q
12 passed in ~2s (zero skips)
.venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85
126 passed, 92.60% — 0 skipped
ss -ltn → 127.0.0.1:5432 (loopback only, nothing toward the LAN)
docker compose down             # without -v, volume kept
```

Teardown: `docker compose down` (without `-v`, volume kept).

No secrets logged: DSNs/passwords never printed; `.env` (git-ignored) only read
via the test `_load_dotenv()` helper; `git status` shows no `.env` tracked.

---

## 4. Gates

| Gate | Command | Result |
|---|---|---|
| pytest + cov | `PGHOST=172.18.0.2 .venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85` (pre-fix; post-fix runs with no `PGHOST` via loopback publish — same result) | 126 passed, 92.60% (≥85) |
| ruff | `.venv/bin/python -m ruff check src tests` | clean (16 SIM117/I001 auto-fixed via `--fix`, re-verified green) |
| mypy | `.venv/bin/python -m mypy src` | `Success: no issues found in 37 source files` |
| bandit | `.venv/bin/python -m bandit -r src -q` | exit 0, no findings (B608 clean — parameterized only) |
| boundary domain+use-cases | `grep -rE "sqlalchemy\|gradio\|fastapi" src/modules/*/domain src/modules/*/use_cases` | 0 matches |
| DIP imports | `grep "from src.modules" ... \| grep infrastructure` in domain/use-cases | 0 (word “infrastructure” appears only in a use-case docstring, not an import) |
| psycopg2 scope | `grep -rn psycopg2 src/` | only `*/infrastructure/*` (+ docstrings) |
| SQL injection construction | `grep -rnE f-string SQL` in infra | 0 f-string SQL |
| compose | `docker compose config` | valid (exit 0, `DATABASE_URL` interpolates) |
| live db | `up -d postgres` → healthy → 12 live passed → `down` (no `-v`) | ok |

---

## 5. Verdict + %

VERDICT: PASS — all TSK-014 contracts implemented, isolated per user, and verified
live against postgres:16 with all DoD gates green.

- New live integration tests: 12/12 passed (100%).
- Full suite: 126/126 passed (114 baseline held, +12 new).
- Coverage: 92.60% total (≥85% gate).
- Static/security/boundary: ruff clean, mypy clean, bandit clean, boundary 0.
- TSK-014 ready for `[x]` closure. Next: TSK-015 (AuthN/AuthZ middleware + scans).

---

## Appendix — Decision table

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Driver | `psycopg2-binary` vs `psycopg` (source build) vs `SQLAlchemy` | `psycopg2-binary` 2.9.13 (wheels bundle libpq, no system build deps); installed into `.venv` + added to `Dockerfile` pip line | Zero build toolchain needed on slim image and dev host; smallest thin-adapter footprint. If install had failed, the honest fallback was to document the block — it succeeded, so no fallback needed. |
| No ORM | `SQLAlchemy` ORM vs raw `psycopg2` SQL | Raw parameterized SQL (`%s` only, no f-strings) | Keeps the adapter thin and auditable; overlap predicate and user-scoping are one-line `WHERE` clauses; avoids ORM import surface in the hexagonal boundary; `bandit` B608 clean by construction. |
| Transaction scope | Port `save()` only vs port + new port methods vs adapter-local helper | Port `save()` persists the appointment row; adapter-local `save_with_notes(appt, notes)` persists appointment + `session_notes` in ONE `with connect():` transaction; `find_notes_by_appointment_and_user_id` reads notes user-scoped | Honors T10-D1 (no new port methods — `CompleteAppointment` validates via `attach_notes` and saves the aggregate) while still exercising the V002 `session_notes` table atomically (single commit/rollback, ownership pre-checked, `updated_at=now()` on conflict). |
| T7-D4 outcome | Add `delete_by_id_and_user_id` now vs defer | Deferred (NOT implemented) | No MUST use-case requires delete; adding it without a RED cycle from a consumer would be scope creep. Port surface unchanged; upserts are ownership-guarded so no delete-shaped IDOR is introduced. |
| Error model (D3) | Granular exceptions vs unified `*ValidationError` | Kept unified `AppointmentValidationError` / `ClientValidationError` / `UserValidationError` (incl. corrupt-row wrapping) | Matches TSK-007/009/010 audit stance (no oracle, no enumeration); mapping layers re-raise domain errors as-is and wrap only non-domain shapes. |
| Host DB access | Publish postgres ports in compose vs bridge-IP via `PGHOST` | Bridge-IP for this task, SUPERSEDED post-task by loopback publish (`127.0.0.1:5432:5432`; tests still honor `PGHOST` as fallback) | Original no-ports stance was MVP surface minimalism; loopback publish keeps that (LAN-invisible) while removing the silent-skip footgun — verified 12/12 with no `PGHOST`. |
