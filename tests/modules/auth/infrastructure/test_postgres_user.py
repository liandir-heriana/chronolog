"""TSK-014 RED: PostgresUserRepository live integration (stdlib + domain only in prod).

LIVE integration tests — skip unless postgres reachable (never fake green).
Written BEFORE production code — must FAIL on collection with
ModuleNotFoundError until
`src/modules/auth/infrastructure/persistence/postgres_repository.py` exists.

Contracts under test (port IUserRepository):
- save(user) + find_by_email(email) round-trip (id/email/hash preserved).
- Unknown email -> None (no oracle, no crash).
- Same-id re-save upserts (hash update visible).
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from src.modules.auth.domain.entities import User
from src.modules.auth.domain.security import hash_password
from src.modules.auth.domain.value_objects import UserEmail, UserId
from src.modules.auth.infrastructure.persistence.postgres_repository import (
    PostgresUserRepository,
)


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

    for name in ("V001__users_clients.sql", "V002__appointments_session_notes.sql"):
        sql = Path("db/migrations") / name
        with psycopg2.connect(dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql.read_text())


@pytest.fixture()
def dsn() -> str:
    value = _test_dsn()
    _apply_migrations(value)
    import psycopg2  # lazy

    with psycopg2.connect(value) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("TRUNCATE users, clients, appointments, session_notes CASCADE")
    yield value
    with psycopg2.connect(value) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("TRUNCATE users, clients, appointments, session_notes CASCADE")


@NEEDS_PG
class TestPostgresUserRepository:
    def test_save_and_find_by_email_round_trip(self, dsn: str) -> None:
        repo = PostgresUserRepository(dsn)
        user = User(
            id=UserId.generate(),
            email=UserEmail("Ada.Owner@example.com"),
            password_hash=hash_password("correct-horse-99"),
        )

        repo.save(user)
        found = repo.find_by_email(UserEmail("ada.owner@example.com"))

        assert found is not None
        assert found.id == user.id
        assert found.email.value == "ada.owner@example.com"
        assert found.password_hash == user.password_hash

    def test_unknown_email_returns_none(self, dsn: str) -> None:
        repo = PostgresUserRepository(dsn)

        assert repo.find_by_email(UserEmail("nobody@example.com")) is None

    def test_same_id_resave_upserts_hash(self, dsn: str) -> None:
        repo = PostgresUserRepository(dsn)
        user = User(
            id=UserId.generate(),
            email=UserEmail("upsert@example.com"),
            password_hash=hash_password("first-pass-99"),
        )
        repo.save(user)

        updated = User(
            id=user.id,
            email=user.email,
            password_hash=hash_password("second-pass-99"),
        )
        repo.save(updated)

        found = repo.find_by_email(UserEmail("upsert@example.com"))
        assert found is not None
        assert found.id == user.id
        assert found.password_hash == updated.password_hash
