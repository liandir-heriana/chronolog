# ChronoLog DB migrations (TSK-013)

Plain versioned SQL files applied in order with `psql`. No migration framework
(src/ is stdlib-only, zero new runtime deps by design).

## Manifest (apply in this order — filenames sort lexicographically)

| File | Contents | Depends on |
|---|---|---|
| `migrations/V001__users_clients.sql` | `users`, `clients` + `idx_clients_user_id` | — (base) |
| `migrations/V002__appointments_session_notes.sql` | `appointments`, `session_notes` + 3 indexes | V001 (FKs into `users`/`clients`) |
| `migrations/V003__sessions.sql` | `sessions` (`token_hash` PK, `user_id` FK, `expires_at`) + 2 indexes | V001 (FK into `users`) |

All statements are idempotent (`CREATE TABLE IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`): re-applying yields zero errors.

## Apply (live, against local compose postgres)

```bash
cp .env.example .env   # once; .env is git-ignored, never commit it
docker compose up -d postgres
# wait for healthy: docker compose ps / pg_isready

set -a; . ./.env; set +a   # load local creds into env (shell only, never logged)
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f - \
  < db/migrations/V001__users_clients.sql
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f - \
  < db/migrations/V002__appointments_session_notes.sql

# verify
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'
```

## Rollback

No down migrations (greenfield MVP, honest choice): to reset local state,
`docker compose down` keeps data (named volume); `docker compose down -v`
drops it (destructive, local only). Schema changes ship as new `V00N__` files.

## Decisions & evidence

Schema map, decision tables (separate `session_notes` table, no GiST
exclusion, no per-user email uniqueness, CASCADE chains) and the full live
`psql` evidence log: `verify/task13_test.md`.
