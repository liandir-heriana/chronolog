-- ChronoLog V001 — users + clients (TSK-013).
--
-- Idempotent: safe to re-apply (`IF NOT EXISTS` throughout).
-- Apply order: V001 first (no dependencies), then V002 (FKs into these tables).
-- See db/README.md for the apply procedure and the decision log
-- (full rationale in verify/task13_test.md, Section 1).
--
-- Conventions mirrored from the pure domain (source of truth):
--   * All ids are UUIDs (UserId / ClientId value objects are canonical UUID strings),
--     hence native UUID PKs with gen_random_uuid() defaults (built into Postgres 13+,
--     no extension needed on postgres:16).
--   * users.email is stored lowercase by the domain (UserEmail normalizes); therefore
--     plain TEXT + UNIQUE is sufficient — no citext extension dependency.
--   * clients.email is deliberately NOT unique per user: the domain defines no such
--     rule (e.g. shared family email), so the DB must not invent one.

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE
        CHECK (char_length(email) >= 3 AND char_length(email) <= 254),
    password_hash TEXT NOT NULL
        CHECK (char_length(password_hash) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL
        CHECK (char_length(btrim(name)) > 0),
    email TEXT NOT NULL
        CHECK (char_length(email) >= 3 AND char_length(email) <= 254),
    phone TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- AuthZ fast path: every client lookup is scoped by user_id
-- (IClientRepository.find_by_id_and_user_id / list_by_user_id in TSK-014).
CREATE INDEX IF NOT EXISTS idx_clients_user_id ON clients (user_id);
