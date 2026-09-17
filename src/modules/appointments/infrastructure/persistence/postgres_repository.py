"""ChronoLog PostgresAppointmentRepository (adapter, psycopg2 only).

Implements the ``IAppointmentRepository`` port with raw parameterized SQL
(``%s`` placeholders only, no f-strings). Every read is scoped by
``user_id`` (IDOR prevention); overlap uses half-open ``[S,E)`` semantics
via ``starts_at < %s AND %s < ends_at``. The aggregate (appointment +
session notes) persists in ONE transaction via ``save_with_notes``; the
port stays frozen per T10-D1 (no new port methods — the notes helpers are
adapter-local). Depends only on the domain port/entities plus stdlib
``os`` (``DATABASE_URL``) and ``psycopg2``.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg2  # type: ignore[import-untyped]

from src.modules.appointments.domain.entities import (
    Appointment,
    AppointmentStatus,
    SessionNotes,
)
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import (
    AppointmentId,
    SessionNoteId,
)


def _require_dsn(dsn: str | None) -> str:
    value = dsn or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return value


def _row_to_appointment(row: tuple[Any, ...]) -> Appointment:
    """Map a ``(id, user_id, client_id, starts_at, ends_at, status)`` row.

    Domain constructors raise domain errors on corrupt data; unexpected
    shapes and unknown status values are wrapped as
    ``AppointmentValidationError`` (never raw crash).
    """
    try:
        raw_id = row[0]
        raw_user_id = row[1]
        raw_client_id = row[2]
        raw_starts = row[3]
        raw_ends = row[4]
        raw_status = row[5]
        if not isinstance(raw_starts, datetime) or raw_starts.tzinfo is None:
            raise AppointmentValidationError("Corrupt appointment starts_at")
        if not isinstance(raw_ends, datetime) or raw_ends.tzinfo is None:
            raise AppointmentValidationError("Corrupt appointment ends_at")
        try:
            status = AppointmentStatus(str(raw_status))
        except ValueError as exc:
            raise AppointmentValidationError(
                f"Corrupt appointment status: {raw_status!r}"
            ) from exc
        return Appointment(
            id=AppointmentId(str(raw_id)),
            user_id=str(raw_user_id),
            client_id=str(raw_client_id),
            starts_at=raw_starts,
            ends_at=raw_ends,
            status=status,
        )
    except AppointmentValidationError:
        raise
    except (IndexError, TypeError, ValueError, AttributeError) as exc:
        raise AppointmentValidationError(f"Corrupt appointment row: {exc}") from exc


def _row_to_notes(row: tuple[Any, ...]) -> SessionNotes:
    """Map a ``(id, appointment_id, user_id, content, created_at)`` row."""
    try:
        raw_id = row[0]
        raw_appointment_id = row[1]
        raw_user_id = row[2]
        raw_content = row[3]
        raw_created = row[4]
        if not isinstance(raw_created, datetime) or raw_created.tzinfo is None:
            raise AppointmentValidationError("Corrupt session notes created_at")
        return SessionNotes(
            id=SessionNoteId(str(raw_id)),
            appointment_id=AppointmentId(str(raw_appointment_id)),
            user_id=str(raw_user_id),
            content=str(raw_content),
            created_at=raw_created,
        )
    except AppointmentValidationError:
        raise
    except (IndexError, TypeError, ValueError, AttributeError) as exc:
        raise AppointmentValidationError(f"Corrupt session notes row: {exc}") from exc


class PostgresAppointmentRepository(IAppointmentRepository):
    """PostgreSQL adapter for the Appointment aggregate root."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = _require_dsn(dsn)

    def save(self, appointment: Appointment) -> None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO appointments"
                " (id, user_id, client_id, starts_at, ends_at, status)"
                " VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET"
                " user_id = EXCLUDED.user_id,"
                " client_id = EXCLUDED.client_id,"
                " starts_at = EXCLUDED.starts_at,"
                " ends_at = EXCLUDED.ends_at,"
                " status = EXCLUDED.status"
                " WHERE appointments.user_id = EXCLUDED.user_id",
                (
                    appointment.id.value,
                    appointment.user_id,
                    appointment.client_id,
                    appointment.starts_at,
                    appointment.ends_at,
                    appointment.status.value,
                ),
            )

    def save_with_notes(self, appointment: Appointment, notes: SessionNotes) -> None:
        """Persist the aggregate (appointment + notes) in ONE transaction.

        Adapter-local helper (not a port method — the ``IAppointmentRepository``
        port stays frozen per T10-D1). Bound-identity mismatches raise the
        unified ``AppointmentValidationError`` before any write.
        """
        if notes.appointment_id != appointment.id:
            raise AppointmentValidationError("Notes belong to another appointment")
        if notes.user_id != appointment.user_id:
            raise AppointmentValidationError("Notes belong to another user")
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO appointments"
                " (id, user_id, client_id, starts_at, ends_at, status)"
                " VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET"
                " user_id = EXCLUDED.user_id,"
                " client_id = EXCLUDED.client_id,"
                " starts_at = EXCLUDED.starts_at,"
                " ends_at = EXCLUDED.ends_at,"
                " status = EXCLUDED.status"
                " WHERE appointments.user_id = EXCLUDED.user_id",
                (
                    appointment.id.value,
                    appointment.user_id,
                    appointment.client_id,
                    appointment.starts_at,
                    appointment.ends_at,
                    appointment.status.value,
                ),
            )
            cur.execute(
                "INSERT INTO session_notes (id, appointment_id, user_id, content)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (appointment_id) DO UPDATE SET"
                " id = EXCLUDED.id,"
                " user_id = EXCLUDED.user_id,"
                " content = EXCLUDED.content,"
                " updated_at = now()"
                " WHERE session_notes.user_id = EXCLUDED.user_id",
                (
                    notes.id.value,
                    notes.appointment_id.value,
                    notes.user_id,
                    notes.content,
                ),
            )

    def find_notes_by_appointment_and_user_id(
        self, appointment_id: AppointmentId, user_id: str
    ) -> SessionNotes | None:
        """Return the notes bound to ``appointment_id`` owned by ``user_id``."""
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, appointment_id, user_id, content, created_at"
                " FROM session_notes WHERE appointment_id = %s AND user_id = %s",
                (appointment_id.value, user_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_notes(row)

    def find_by_id_and_user_id(
        self, appointment_id: AppointmentId, user_id: str
    ) -> Appointment | None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, client_id, starts_at, ends_at, status"
                " FROM appointments WHERE id = %s AND user_id = %s",
                (appointment_id.value, user_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_appointment(row)

    def list_by_user_id(self, user_id: str) -> list[Appointment]:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, client_id, starts_at, ends_at, status"
                " FROM appointments WHERE user_id = %s ORDER BY starts_at, id",
                (user_id,),
            )
            rows = cur.fetchall()
        return [_row_to_appointment(row) for row in rows]

    def list_by_client_and_user_id(
        self, client_id: str, user_id: str
    ) -> list[Appointment]:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, client_id, starts_at, ends_at, status"
                " FROM appointments WHERE client_id = %s AND user_id = %s"
                " ORDER BY starts_at, id",
                (client_id, user_id),
            )
            rows = cur.fetchall()
        return [_row_to_appointment(row) for row in rows]

    def list_overlapping(
        self,
        user_id: str,
        starts_at: datetime,
        ends_at: datetime,
        exclude_appointment_id: AppointmentId | None = None,
    ) -> list[Appointment]:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            if exclude_appointment_id is None:
                cur.execute(
                    "SELECT id, user_id, client_id, starts_at, ends_at, status"
                    " FROM appointments"
                    " WHERE user_id = %s AND starts_at < %s AND %s < ends_at"
                    " ORDER BY starts_at, id",
                    (user_id, ends_at, starts_at),
                )
            else:
                cur.execute(
                    "SELECT id, user_id, client_id, starts_at, ends_at, status"
                    " FROM appointments"
                    " WHERE user_id = %s AND starts_at < %s AND %s < ends_at"
                    " AND id != %s ORDER BY starts_at, id",
                    (user_id, ends_at, starts_at, exclude_appointment_id.value),
                )
            rows = cur.fetchall()
        return [_row_to_appointment(row) for row in rows]
