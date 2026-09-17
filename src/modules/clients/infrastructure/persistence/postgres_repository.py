"""ChronoLog PostgresClientRepository (adapter, psycopg2 only).

Implements the ``IClientRepository`` port with raw parameterized SQL
(``%s`` placeholders only, no f-strings). Every read is scoped by
``user_id`` (IDOR prevention); the upsert re-save is ownership-guarded so
a foreign ``user_id`` can never hijack an existing row. Depends only on
the domain port/entities plus stdlib ``os`` (``DATABASE_URL``) and
``psycopg2``.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg2  # type: ignore[import-untyped]

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.exceptions import ClientValidationError
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId, Email, Phone


def _require_dsn(dsn: str | None) -> str:
    value = dsn or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return value


def _row_to_client(row: tuple[Any, ...]) -> Client:
    """Map a ``(id, user_id, name, email, phone)`` row to a Client.

    Domain value objects raise domain errors on corrupt data; unexpected
    shapes are wrapped as ``ClientValidationError`` (never raw crash).
    """
    try:
        raw_id = row[0]
        raw_user_id = row[1]
        raw_name = row[2]
        raw_email = row[3]
        raw_phone = row[4]
        phone = Phone(str(raw_phone)) if raw_phone is not None else None
        return Client(
            id=ClientId(str(raw_id)),
            user_id=str(raw_user_id),
            name=str(raw_name),
            email=Email(str(raw_email)),
            phone=phone,
        )
    except ClientValidationError:
        raise
    except (IndexError, TypeError, ValueError, AttributeError) as exc:
        raise ClientValidationError(f"Corrupt client row: {exc}") from exc


class PostgresClientRepository(IClientRepository):
    """PostgreSQL adapter for the Client aggregate root."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = _require_dsn(dsn)

    def save(self, client: Client) -> None:
        phone_value = client.phone.value if client.phone is not None else None
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clients (id, user_id, name, email, phone)"
                " VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET"
                " user_id = EXCLUDED.user_id,"
                " name = EXCLUDED.name,"
                " email = EXCLUDED.email,"
                " phone = EXCLUDED.phone"
                " WHERE clients.user_id = EXCLUDED.user_id",
                (
                    client.id.value,
                    client.user_id,
                    client.name,
                    client.email.value,
                    phone_value,
                ),
            )

    def find_by_id_and_user_id(
        self, client_id: ClientId, user_id: str
    ) -> Client | None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, name, email, phone FROM clients"
                " WHERE id = %s AND user_id = %s",
                (client_id.value, user_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_client(row)

    def list_by_user_id(self, user_id: str) -> list[Client]:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, name, email, phone FROM clients"
                " WHERE user_id = %s ORDER BY created_at, id",
                (user_id,),
            )
            rows = cur.fetchall()
        return [_row_to_client(row) for row in rows]
