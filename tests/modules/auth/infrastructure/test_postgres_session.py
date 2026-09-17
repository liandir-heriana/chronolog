"""TSK-016 RED: PostgresSessionRepository live integration (D3 persistence).

LIVE integration tests — skip unless postgres reachable (never fake green).
Written BEFORE production code — must FAIL on collection with
ModuleNotFoundError until
`src/modules/auth/infrastructure/persistence/postgres_session_repository.py`
exists and `ISessionRepository` is defined.

Contract (verify/task15_test.md §3.1): `sessions(token_hash PK, user_id FK,
expires_at, created_at)` stores `sha256(token)`, never the raw token.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.modules.auth.domain.entities import AuthSession
from src.modules.auth.domain.security import hash_token
from src.modules.auth.infrastructure.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)

NOW = datetime(2026, 9, 17, 9, 55, tzinfo=UTC)


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = raw.strip().strip("'").strip('"')


_load_dotenv()


def _pg_params() -> tuple[str, int, str, str, str]:
    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    user = os.getenv("POSTGRES_USER", "chronolog")
    password = os.getenv("POSTGRES_PASSWORD", "chronolog")
    db = os.getenv("POSTGRES_DB", "chronolog")
    return host, port, user, password, db


def _test_dsn() -> str:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override
    host, port, user, password, db = _pg_params()
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _postgres_reachable() -> bool:
    host, port, _, _, _ = _pg_params()
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


NEEDS_PG = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="postgres not reachable (live integration, no fake green)",
)


def _apply_migrations(dsn: str) -> None:
    import psycopg2  # lazy: RED must fail on adapter import, not here

    for name in (
        "V001__users_clients.sql",
        "V002__appointments_session_notes.sql",
        "V003__sessions.sql",
    ):
        sql = Path("db/migrations") / name
        with psycopg2.connect(dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql.read_text())


def _ensure_user(dsn: str, user_id: str, email: str) -> None:
    import psycopg2  # lazy

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)"
            " ON CONFLICT (id) DO NOTHING",
            (user_id, email, "dummy-hash-for-fk-setup"),
        )


@pytest.fixture()
def dsn() -> str:
    value = _test_dsn()
    _apply_migrations(value)
    import psycopg2  # lazy

    with psycopg2.connect(value) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("TRUNCATE users, clients, appointments, session_notes, sessions CASCADE")
    yield value
    with psycopg2.connect(value) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("TRUNCATE users, clients, appointments, session_notes, sessions CASCADE")


@NEEDS_PG
class TestPostgresSessionRepository:
    def test_save_find_round_trip_stores_hash_not_token(self, dsn: str) -> None:
        from uuid import uuid4

        import psycopg2

        owner = str(uuid4())
        _ensure_user(dsn, owner, f"{owner}@example.com")
        repo = PostgresSessionRepository(dsn)
        session = AuthSession.issue(owner)

        repo.save(session)
        found = repo.find_by_token_hash(hash_token(session.token))

        assert found is not None
        assert found.user_id == owner
        assert found.expires_at == session.expires_at

        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT token_hash FROM sessions")
            (stored_hash,) = cur.fetchone()  # type: ignore[misc]
        assert stored_hash == hash_token(session.token)
        assert session.token not in stored_hash

    def test_unknown_hash_returns_none(self, dsn: str) -> None:
        repo = PostgresSessionRepository(dsn)
        assert repo.find_by_token_hash("0" * 64) is None

    def test_logout_deletes_session(self, dsn: str) -> None:
        from uuid import uuid4

        owner = str(uuid4())
        _ensure_user(dsn, owner, f"{owner}@example.com")
        repo = PostgresSessionRepository(dsn)
        session = AuthSession.issue(owner)
        repo.save(session)

        repo.delete_by_token_hash(hash_token(session.token))
        assert repo.find_by_token_hash(hash_token(session.token)) is None

    def test_janitor_deletes_only_expired(self, dsn: str) -> None:
        from uuid import uuid4

        owner = str(uuid4())
        _ensure_user(dsn, owner, f"{owner}@example.com")
        repo = PostgresSessionRepository(dsn)
        live = AuthSession.issue(owner, ttl_hours=12)
        dead = AuthSession.issue(owner, ttl_hours=-1)
        repo.save(live)
        repo.save(dead)

        removed = repo.delete_expired(datetime.now(UTC))
        assert removed == 1
        assert repo.find_by_token_hash(hash_token(live.token)) is not None
        assert repo.find_by_token_hash(hash_token(dead.token)) is None

    def test_user_cascade_wipes_sessions(self, dsn: str) -> None:
        from uuid import uuid4

        import psycopg2

        owner = str(uuid4())
        _ensure_user(dsn, owner, f"{owner}@example.com")
        repo = PostgresSessionRepository(dsn)
        session = AuthSession.issue(owner)
        repo.save(session)

        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (owner,))
        assert repo.find_by_token_hash(hash_token(session.token)) is None
