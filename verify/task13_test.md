# TSK-013 Verification Report — SQL Schema Design & Migration Scripts

**Target:** `TSK-013: SQL Database Schema Design & Migration Scripts`
**Assignee:** `@devops-engineer` — **Route:** `skill({name:"devops-docker"})`
**Started:** 2026-09-16 14:34 (UTC) — **Completed:** 2026-09-16 14:53 (UTC)
**Branch:** `feature/TSK-013-sql-schema-migrations` (reused current branch, none created)
**Artifacts:** `db/migrations/V001__users_clients.sql`, `db/migrations/V002__appointments_session_notes.sql`, `db/README.md`

---

## 1. Schema map & design decisions

### 1.1 Final schema (PostgreSQL 16, native types, zero extensions)

| Table | Columns | PK / UNIQUE | FKs (all `ON DELETE CASCADE`) | Indexes |
|---|---|---|---|---|
| `users` | `id UUID DEFAULT gen_random_uuid()`, `email TEXT UNIQUE NOT NULL` (len 3–254), `password_hash TEXT NOT NULL` (non-empty), `created_at TIMESTAMPTZ DEFAULT now()` | PK `(id)`, UQ `(email)` | — | pkey, `users_email_key` |
| `clients` | `id UUID`, `user_id UUID NOT NULL`, `name VARCHAR(100) NOT NULL` (non-blank after trim), `email TEXT NOT NULL` (len 3–254), `phone TEXT NULL`, `created_at` | PK `(id)` | `user_id → users(id)` | pkey, `idx_clients_user_id (user_id)` |
| `appointments` | `id UUID`, `user_id UUID NOT NULL`, `client_id UUID NOT NULL`, `starts_at / ends_at TIMESTAMPTZ NOT NULL`, `status TEXT DEFAULT 'scheduled'` ∈ {scheduled, completed, cancelled} (lowercase = `AppointmentStatus` enum), `created_at` | PK `(id)` | `user_id → users(id)`, `client_id → clients(id)` | pkey, `idx_appointments_user_starts (user_id, starts_at)`, `idx_appointments_client (client_id)` |
| `session_notes` | `id UUID`, `appointment_id UUID NOT NULL UNIQUE`, `user_id UUID NOT NULL`, `content TEXT NOT NULL` (non-blank, ≤5000 chars = domain `_MAX_CONTENT_LEN`), `created_at`, `updated_at` (both `DEFAULT now()`) | PK `(id)`, UQ `(appointment_id)` | `appointment_id → appointments(id)`, `user_id → users(id)` | pkey, UQ backing index, `idx_session_notes_user_id (user_id)` |

Migration split: **V001** (`users`, `clients` — no dependencies) → **V002**
(`appointments`, `session_notes` — FKs into V001 tables). Every statement uses
`IF NOT EXISTS`; re-apply is a no-op (only NOTICEs, exit 0). `updated_at` is
maintained application-side by the TSK-014 adapter (no trigger — keeps
migrations dependency-free). No `citext`, no `btree_gist`, no framework.

### 1.2 Decision tables

**D1 — session_notes: separate table vs. columns on appointments?**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| A. Columns on `appointments` (`notes_content`, …) | 1 table, trivial save | Wide rows; no `updated_at` history without more columns; notes lifecycle (edit-after-complete, TSK-006 rule) has nowhere to live; diverges from spec | ❌ rejected |
| B. Separate `session_notes` table, `appointment_id UNIQUE` FK | Narrow rows; 1:1 enforced by DB; `updated_at` tracking; TSK-014 adapter flexibility (aggregate saved in one transaction across both tables); matches domain `SessionNotes` entity 1:1 | One JOIN on read | ✅ **chosen** |

Justification: T10-D1 ("notes persist WITH the appointment aggregate") is a
*logical* aggregate rule, not a physical one-row rule — the adapter upholds it
by writing both tables in a single transaction. The UNIQUE constraint makes
the 1:1 invariant machine-checked instead of convention.

**D2 — overlap prevention: GiST exclusion constraint vs. application-level?**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| A. `EXCLUDE USING gist (user_id WITH =, tstzrange(starts_at,ends_at) WITH &&)` (+ partial `WHERE status='scheduled'`) | DB-hardened no-overlap | Needs `btree_gist` extension; half-open/adjacency + cancelled-appointment semantics must duplicate domain logic in DDL → dual-enforcement drift risk; harder to evolve | ❌ rejected |
| B. Application-level (`ScheduleAppointment` + `list_overlapping` query in TSK-014), DB keeps minimum `CHECK (ends_at > starts_at)` | Single source of truth (domain owns the rule, already TDD-covered in TSK-009); zero extensions; cancelled/completed windows stay queryable | Overlap not enforced if a future writer bypasses the use-case | ✅ **chosen** |

Justification: the overlap rule (half-open `[S,E)`, same-user scope, adjacent
allowed) is already specified and tested in the domain. Re-implementing it in
DDL buys little and risks divergence. The exclusion can be added later as a
`V00N__` migration if TSK-015 audit demands defense-in-depth.

**D3 — other recorded choices:** no `UNIQUE(user_id, email)` on clients (domain
defines no such rule — e.g. shared family email — DB must not invent one);
`client_id → clients` is `CASCADE` not `RESTRICT` (keeps the
user→clients→appointments→notes wipe chain orphan-free; no delete use-case
exists in MUST scope per T7-D4); `users.email` is plain `TEXT+UNIQUE`
(domain `UserEmail` already lowercases — no `citext` extension needed); all ids
are native `UUID` (every domain Id VO is a canonical UUID string).

---

## 2. Checklist

- [x] `users`, `clients`, `appointments`, `session_notes` tables with UUID PKs
- [x] All 5 FKs present, all `ON DELETE CASCADE` (verified from `pg_constraint`)
- [x] `user_id` indexed on `clients` / `appointments` (composite w/ `starts_at`) / `session_notes`
- [x] `CHECK (ends_at > starts_at)`, status allow-list, content length/non-blank guards
- [x] Migrations applied LIVE in order, re-applied clean (idempotent)
- [x] Smoke round-trip: user → client (+NULL-phone client) → appointment (default `scheduled`) → `completed` → notes → JOIN read
- [x] 5 negative inserts rejected (2×FK, window CHECK, status CHECK, notes UNIQUE)
- [x] Cascade wipe verified (`DELETE user` → all 4 tables empty), DB left pristine
- [x] No secrets in `db/` (only `$POSTGRES_PASSWORD` runtime references); `.env` untouched & git-ignored
- [x] `docker compose down` (volume kept, no `-v`); pytest baseline 114 passed

---

## 3. Live evidence (psql, postgres:16, 2026-09-16 ~14:35–14:37 UTC)

**Apply (exit 0):** V001 → `CREATE TABLE, CREATE TABLE, CREATE INDEX`;
V002 → `CREATE TABLE, CREATE INDEX, CREATE INDEX, CREATE TABLE, CREATE INDEX`.
**Re-apply (exit 0):** only `NOTICE: relation ... already exists, skipping`.

**`\dt`:** `appointments | clients | session_notes | users`
(+ pre-existing `probe` table from TSK-012.1 — inspected, left untouched).

**FKs (`pg_constraint`):**

```text
clients       | clients_user_id_fkey              | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
appointments  | appointments_client_id_fkey       | FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
appointments  | appointments_user_id_fkey         | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
session_notes | session_notes_appointment_id_fkey | FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE
session_notes | session_notes_user_id_fkey        | FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
```

**Indexes (`pg_indexes`, public):** `users_pkey`, `users_email_key`,
`clients_pkey`, `idx_clients_user_id`, `appointments_pkey`,
`idx_appointments_user_starts (user_id, starts_at)`,
`idx_appointments_client (client_id)`, `session_notes_pkey`,
`session_notes_appointment_id_key (UNIQUE)`, `idx_session_notes_user_id`.

**`\d` per table:** all columns/defaults/CHECKs/FKs as §1.1 —
`users_email_check`, `clients_name_check`, `appointments_window_check`,
`appointments_status_check`, `session_notes_content_check`,
`status DEFAULT 'scheduled'`, all `created_at/updated_at DEFAULT now()`.

**Round-trip (exit 0):** user `pro@chronolog.test` → clients `Ada Lovelace`
(with phone) + `No Phone` (NULL phone) → appointment `scheduled` (default) →
`UPDATE … completed` → notes `First session: goals review.` → 4-table JOIN
returned 1 row `(pro@chronolog.test, Ada Lovelace, completed, First session: goals)`.

**Negatives (all exit 1, all correctly rejected):**

```text
N1 ghost client_id  → ERROR violates FK "appointments_client_id_fkey"
N2 ends_at<starts_at → ERROR violates CHECK "appointments_window_check"
N3 status RESCHEDULED → ERROR violates CHECK "appointments_status_check"
N4 2nd notes/same appt → ERROR violates UNIQUE "session_notes_appointment_id_key"
N5 ghost user_id      → ERROR violates FK "clients_user_id_fkey"
```

**Cascade wipe:** `DELETE FROM users … → DELETE 1`; counts
`users/clients/appointments/session_notes = 0/0/0/0`.

**Infra:** `docker compose up -d postgres` → `Up (healthy)`,
`pg_isready … accepting connections (exit 0)`; closed with
`docker compose down` (containers+network removed, `chronolog-pgdata` kept).

---

## 4. Gates

| Gate | Result |
|---|---|
| Migration order + idempotency (live) | ✅ V001→V002 exit 0; re-apply exit 0 (NOTICEs only) |
| Schema integrity (FKs + `user_id` indexes, live catalog) | ✅ 5 FKs, 4 `user_id` index paths, all CHECKs |
| Smoke + negative tests (live) | ✅ 1 round-trip + 5/5 rejections + cascade wipe |
| Secrets (no values in `db/`, `.env` ignored/untouched) | ✅ `git check-ignore .env` OK; `db/` holds only `$VAR` references |
| Python gates | N/A — no `.py` added/changed; baseline `.venv pytest` **114 passed** (no regression) |
| `ruff` / `mypy` / `bandit` | N/A — SQL+Markdown only |
| Boundary grep (`sqlalchemy|gradio|fastapi` in `domain/`) | N/A — `domain/` untouched |

---

## 5. Verdict + progress

**Verdict: PASS — TSK-013 Done.** Schema mirrors the domain VOs 1:1, every
AuthZ-relevant column is indexed, constraints are proven live (not just
declared), migrations are ordered + idempotent, and the database was left
pristine with the stack shut down cleanly.

Independently re-verified 2026-09-16 (parallel verification, ~90% alignment):
4 tables confirmed alive in the `chronolog-pgdata` volume across a down/up
cycle; live catalog re-checked — 5 FKs + all CHECKs (`window`, `status`,
`content`, emails, password) present; final counts 0/0/0/0 consistent with the
reported cascade wipe. Round-trip/negatives/idempotency taken from the §3
evidence (detailed and consistent); each negative not individually re-run.

**Progress:** 14/20 → **15/20 = 75.00%** `[███████▌░░]`
(Pending 5, In Progress 0, Completed 15).
**Next:** TSK-014 Postgres adapters implement `IClientRepository` /
`IAppointmentRepository` (+ `IUserRepository`) on top of this schema —
recommended: parameterized queries only, `user_id`-scoped reads, overlap lookup
via `(user_id, starts_at)` range scan, aggregate save in one transaction.
