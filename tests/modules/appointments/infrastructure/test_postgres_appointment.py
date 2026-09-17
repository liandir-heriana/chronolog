"""TSK-014 RED: PostgresAppointmentRepository live integration.

LIVE integration tests — skip unless postgres reachable (never fake green).
Written BEFORE production code — must FAIL on collection with
ModuleNotFoundError until
`src/modules/appointments/infrastructure/persistence/postgres_repository.py`
exists.

Contracts under test (port IAppointmentRepository, window model per TSK-009):
- save + find_by_id_and_user_id + list_by_user_id +
  list_by_client_and_user_id round-trip (window/status preserved).
- Cross-user invisibility on every read (IDOR).
- list_overlapping half-open [S,E): overlapping seed hits, adjacent window
  misses, other-user window invisible, exclude_appointment_id skips self.
- Complete + attach_notes aggregate save (T10-D1): status COMPLETED persists
  and notes re-attach on the reloaded aggregate; notes row round-trips via
  the adapter-local save_with_notes / find_notes helpers in ONE transaction
  (helpers are adapter-local, the port stays frozen — no new port methods).
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.modules.appointments.domain.entities import (
    Appointment,
    AppointmentStatus,
)
from src.modules.appointments.domain.value_objects import AppointmentId
from src.modules.appointments.infrastructure.persistence.postgres_repository import (
    PostgresAppointmentRepository,
)

BASE_START = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
BASE_END = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


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


def _ensure_client(dsn: str, client_id: str, user_id: str) -> None:
    import psycopg2  # lazy

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO clients (id, user_id, name, email) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (id) DO NOTHING",
            (client_id, user_id, "Seed Client", f"{client_id}@example.com"),
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


def _seed_owner(dsn: str) -> tuple[str, str]:
    from uuid import uuid4

    owner = str(uuid4())
    client_id = str(uuid4())
    _ensure_user(dsn, owner, f"{owner}@example.com")
    _ensure_client(dsn, client_id, owner)
    return owner, client_id


@NEEDS_PG
class TestPostgresAppointmentRoundTrip:
    def test_save_find_list_by_client(self, dsn: str) -> None:
        owner, client_id = _seed_owner(dsn)
        repo = PostgresAppointmentRepository(dsn)
        appt = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id=owner,
            client_id=client_id,
            starts_at=BASE_START,
            ends_at=BASE_END,
            now=NOW,
        )

        repo.save(appt)
        found = repo.find_by_id_and_user_id(appt.id, owner)
        by_user = repo.list_by_user_id(owner)
        by_client = repo.list_by_client_and_user_id(client_id, owner)

        assert found is not None
        assert found.id == appt.id
        assert found.user_id == owner
        assert found.client_id == client_id
        assert found.starts_at == BASE_START
        assert found.ends_at == BASE_END
        assert found.status is AppointmentStatus.SCHEDULED
        assert [a.id for a in by_user] == [appt.id]
        assert [a.id for a in by_client] == [appt.id]

    def test_cross_user_invisibility(self, dsn: str) -> None:
        from uuid import uuid4

        owner, client_id = _seed_owner(dsn)
        attacker = str(uuid4())
        _ensure_user(dsn, attacker, f"{attacker}@example.com")
        repo = PostgresAppointmentRepository(dsn)
        appt = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id=owner,
            client_id=client_id,
            starts_at=BASE_START,
            ends_at=BASE_END,
            now=NOW,
        )
        repo.save(appt)

        assert repo.find_by_id_and_user_id(appt.id, attacker) is None
        assert repo.list_by_user_id(attacker) == []
        assert repo.list_by_client_and_user_id(client_id, attacker) == []


@NEEDS_PG
class TestPostgresAppointmentOverlap:
    def test_overlapping_hits_adjacent_misses_excluded_self(self, dsn: str) -> None:
        owner, client_id = _seed_owner(dsn)
        repo = PostgresAppointmentRepository(dsn)
        base = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id=owner,
            client_id=client_id,
            starts_at=BASE_START,
            ends_at=BASE_END,
            now=NOW,
        )
        repo.save(base)

        overlapping = repo.list_overlapping(
            owner,
            BASE_START + timedelta(minutes=30),
            BASE_END + timedelta(minutes=30),
        )
        adjacent = repo.list_overlapping(owner, BASE_END, BASE_END + timedelta(hours=1))
        excluded = repo.list_overlapping(
            owner,
            BASE_START + timedelta(minutes=30),
            BASE_END + timedelta(minutes=30),
            exclude_appointment_id=base.id,
        )

        assert [a.id for a in overlapping] == [base.id]
        assert adjacent == []
        assert excluded == []

    def test_other_user_window_invisible(self, dsn: str) -> None:
        from uuid import uuid4

        owner, client_id = _seed_owner(dsn)
        other = str(uuid4())
        other_client = str(uuid4())
        _ensure_user(dsn, other, f"{other}@example.com")
        _ensure_client(dsn, other_client, other)
        repo = PostgresAppointmentRepository(dsn)
        repo.save(
            Appointment.schedule(
                id=AppointmentId.generate(),
                user_id=other,
                client_id=other_client,
                starts_at=BASE_START,
                ends_at=BASE_END,
                now=NOW,
            )
        )
        own = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id=owner,
            client_id=client_id,
            starts_at=BASE_START + timedelta(hours=5),
            ends_at=BASE_END + timedelta(hours=5),
            now=NOW,
        )
        repo.save(own)

        hits = repo.list_overlapping(
            owner, BASE_START, BASE_END
        )
        assert hits == []


@NEEDS_PG
class TestPostgresAppointmentNotesAggregate:
    def test_complete_persists_and_notes_reattach(self, dsn: str) -> None:
        owner, client_id = _seed_owner(dsn)
        repo = PostgresAppointmentRepository(dsn)
        appt = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id=owner,
            client_id=client_id,
            starts_at=BASE_START,
            ends_at=BASE_END,
            now=NOW,
        )
        repo.save(appt)

        stored = repo.find_by_id_and_user_id(appt.id, owner)
        assert stored is not None
        stored.complete()
        notes = stored.attach_notes("First session went well.")
        repo.save_with_notes(stored, notes)

        reloaded = repo.find_by_id_and_user_id(appt.id, owner)
        assert reloaded is not None
        assert reloaded.status is AppointmentStatus.COMPLETED
        # Aggregate integrity: notes re-attach on the COMPLETED reload.
        rebound = reloaded.attach_notes("First session went well.")
        assert rebound.user_id == owner
        assert rebound.appointment_id == appt.id

        persisted = repo.find_notes_by_appointment_and_user_id(appt.id, owner)
        assert persisted is not None
        assert persisted.content == "First session went well."
        assert persisted.user_id == owner

        # Notes are user-scoped too: attacker sees neither appointment nor notes.
        from uuid import uuid4

        attacker = str(uuid4())
        _ensure_user(dsn, attacker, f"{attacker}@example.com")
        assert repo.find_notes_by_appointment_and_user_id(appt.id, attacker) is None
