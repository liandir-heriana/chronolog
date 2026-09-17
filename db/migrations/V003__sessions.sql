-- ChronoLog V003 — sessions (TSK-016 D3).
--
-- Idempotent: safe to re-apply (`IF NOT EXISTS` throughout).
-- Apply order: AFTER V001 (FK into users). See db/README.md.
--
-- Decisions (full rationale in verify/task16_test.md, Section 1):
--   * `token_hash TEXT PRIMARY KEY` stores sha256(token) hex (64 chars),
--     NEVER the raw bearer token — a DB leak alone cannot impersonate.
--     Lookup hashes the presented token (`hash_token` in
--     `src/modules/auth/domain/security.py`).
--   * `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE` so a
--     tenant wipe revokes all sessions atomically (logout/kick by delete).
--   * `expires_at TIMESTAMPTZ NOT NULL` enforced by the middleware
--     (`authenticate_request` rejects `now >= expires_at` with the generic
--     `InvalidCredentialsError`); `delete_expired(now)` is the janitor.
--   * No UNIQUE(token) — the hash IS the PK. No session payload beyond
--     owner + expiry (stateless claims would reintroduce JWT leak surface).

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY
        CHECK (char_length(token_hash) = 64),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Middleware fast paths: sessions resolve by hash; janitor scans expiry;
-- per-user revocation lists by user_id.
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions (expires_at);
