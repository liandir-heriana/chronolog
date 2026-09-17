"""TSK-014 RED: PostgresClientRepository live integration.

LIVE integration tests — skip unless postgres reachable (never fake green).
Written BEFORE production code — must FAIL on collection with
ModuleNotFoundError until
`src/modules/clients/infrastructure/persistence/postgres_repository.py` exists.

Contracts under test (port IClientRepository):
- save(client) + find_by_id_and_user_id + list_by_user_id round-trip
  (id/user_id/name/email/phone preserved, NULL phone preserved).
- Cross-user invisibility: foreign user_id -> None / empty list (IDOR).
- Same-id re-save upserts contact fields.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.value_objects import ClientId, Email, Phone
from src.modules.clients.infrastructure.persistence.postgres_repository import (
    PostgresClientRepository,
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
            cur.execute("TRUNCATE users, clients, appointments, session_notes CASCADE")
    yield value
    with psycopg2.connect(value) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("TRUNCATE users, clients, appointments, session_notes CASCADE")


@NEEDS_PG
class TestPostgresClientRepository:
    def test_save_find_list_round_trip(self, dsn: str) -> None:
        from uuid import uuid4

        owner = str(uuid4())
        _ensure_user(dsn, owner, "owner@example.com")
        repo = PostgresClientRepository(dsn)
        client = Client(
            id=ClientId.generate(),
            user_id=owner,
            name="  Alice Smith ",
            email=Email("Alice@Example.COM"),
            phone=Phone("+34 600 111 222"),
        )

        repo.save(client)
        found = repo.find_by_id_and_user_id(client.id, owner)
        listed = repo.list_by_user_id(owner)

        assert found is not None
        assert found.id == client.id
        assert found.user_id == owner
        assert found.name == "Alice Smith"
        assert found.email.value == "alice@example.com"
        assert found.phone is not None and found.phone.value == "+34600111222"
        assert [c.id for c in listed] == [client.id]

    def test_null_phone_round_trip(self, dsn: str) -> None:
        from uuid import uuid4

        owner = str(uuid4())
        _ensure_user(dsn, owner, "nophone@example.com")
        repo = PostgresClientRepository(dsn)
        client = Client(
            id=ClientId.generate(),
            user_id=owner,
            name="No Phone",
            email=Email("nophone-client@example.com"),
            phone=None,
        )

        repo.save(client)
        found = repo.find_by_id_and_user_id(client.id, owner)

        assert found is not None
        assert found.phone is None

    def test_cross_user_invisibility(self, dsn: str) -> None:
        from uuid import uuid4

        owner = str(uuid4())
        attacker = str(uuid4())
        _ensure_user(dsn, owner, "owner2@example.com")
        _ensure_user(dsn, attacker, "attacker@example.com")
        repo = PostgresClientRepository(dsn)
        client = Client(
            id=ClientId.generate(),
            user_id=owner,
            name="Bob",
            email=Email("bob@example.com"),
        )
        repo.save(client)

        assert repo.find_by_id_and_user_id(client.id, attacker) is None
        assert repo.list_by_user_id(attacker) == []
        # Owner still sees it (no oracle leak, no destructive read).
        assert repo.find_by_id_and_user_id(client.id, owner) is not None

    def test_same_id_resave_upserts_contact(self, dsn: str) -> None:
        from uuid import uuid4

        owner = str(uuid4())
        _ensure_user(dsn, owner, "upsert-owner@example.com")
        repo = PostgresClientRepository(dsn)
        client = Client(
            id=ClientId.generate(),
            user_id=owner,
            name="Old Name",
            email=Email("old@example.com"),
        )
        repo.save(client)

        client.update_contact(name="New Name", email=Email("new@example.com"))
        repo.save(client)

        found = repo.find_by_id_and_user_id(client.id, owner)
        assert found is not None
        assert found.name == "New Name"
        assert found.email.value == "new@example.com"
