"""ChronoLog composition root (wiring only, no business rules).

Builds concrete Postgres adapters from ``DATABASE_URL``, injects them into
the pure use-cases, and hands the wired graph to the Gradio presentation
layer. This is the ONLY place (with ``src/main.py``) allowed to import
concrete adapters — ``src/presentation`` receives instances and calls
ports/use-cases, never ``Postgres*`` directly (DIP).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.core.security.rate_limit import LoginRateLimiter
from src.modules.appointments.infrastructure.persistence.postgres_repository import (
    PostgresAppointmentRepository,
)
from src.modules.appointments.use_cases.complete_appointment import CompleteAppointment
from src.modules.appointments.use_cases.get_client_history import GetClientHistory
from src.modules.appointments.use_cases.schedule_appointment import ScheduleAppointment
from src.modules.auth.infrastructure.persistence.postgres_repository import (
    PostgresUserRepository,
)
from src.modules.auth.infrastructure.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)
from src.modules.auth.use_cases.authenticate_user import AuthenticateUser
from src.modules.auth.use_cases.register_user import RegisterUser
from src.modules.clients.infrastructure.persistence.postgres_repository import (
    PostgresClientRepository,
)
from src.modules.clients.use_cases.register_client import RegisterClient

_MIGRATIONS_IN_ORDER = (
    "V001__users_clients.sql",
    "V002__appointments_session_notes.sql",
    "V003__sessions.sql",
)


def resolve_dsn(dsn: str | None = None) -> str:
    """Return the Postgres DSN or raise a clear error (no secret logged)."""
    value = dsn or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return value


def migrations_dir() -> Path:
    """Return the versioned-SQL directory (repo-root ``db/migrations``)."""
    return Path(__file__).resolve().parents[1] / "db" / "migrations"


def ensure_schema(dsn: str | None = None) -> None:
    """Apply V001+V002+V003 idempotently (safe to run on every boot)."""
    import psycopg2  # type: ignore[import-untyped]  # local: composition-only

    target = resolve_dsn(dsn)
    base = migrations_dir()
    with psycopg2.connect(target) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for name in _MIGRATIONS_IN_ORDER:
                cur.execute((base / name).read_text())


@dataclass
class AppContext:
    """Wired application graph (adapters + use-cases + limiter)."""

    dsn: str
    users: PostgresUserRepository
    clients: PostgresClientRepository
    appointments: PostgresAppointmentRepository
    sessions: PostgresSessionRepository
    register_user: RegisterUser
    authenticate_user: AuthenticateUser
    register_client: RegisterClient
    schedule_appointment: ScheduleAppointment
    complete_appointment: CompleteAppointment
    get_history: GetClientHistory
    limiter: LoginRateLimiter


def build_context(
    dsn: str | None = None,
    *,
    max_login_attempts: int = 5,
    login_window_seconds: int = 300,
) -> AppContext:
    """Wire adapters -> use-cases from ``DATABASE_URL`` (no I/O besides env)."""
    target = resolve_dsn(dsn)
    users = PostgresUserRepository(target)
    clients = PostgresClientRepository(target)
    appointments = PostgresAppointmentRepository(target)
    sessions = PostgresSessionRepository(target)
    return AppContext(
        dsn=target,
        users=users,
        clients=clients,
        appointments=appointments,
        sessions=sessions,
        register_user=RegisterUser(users),
        authenticate_user=AuthenticateUser(users),
        register_client=RegisterClient(clients),
        schedule_appointment=ScheduleAppointment(appointments, clients),
        complete_appointment=CompleteAppointment(appointments),
        get_history=GetClientHistory(clients, appointments),
        limiter=LoginRateLimiter(
            max_attempts=max_login_attempts,
            window_seconds=login_window_seconds,
        ),
    )
