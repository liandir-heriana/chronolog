"""ChronoLog PostgresUserRepository (adapter, psycopg2 only).

Implements the ``IUserRepository`` port with raw parameterized SQL
(``%s`` placeholders only, no f-strings). Depends only on the domain
port/entities plus stdlib ``os`` (``DATABASE_URL``) and ``psycopg2``.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg2  # type: ignore[import-untyped]

from src.modules.auth.domain.entities import User
from src.modules.auth.domain.exceptions import UserValidationError
from src.modules.auth.domain.repository_interfaces import IUserRepository
from src.modules.auth.domain.value_objects import UserEmail, UserId


def _require_dsn(dsn: str | None) -> str:
    value = dsn or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return value


def _row_to_user(row: tuple[Any, ...]) -> User:
    """Map a ``(id, email, password_hash)`` row to a User.

    Domain value objects raise domain errors on corrupt data; unexpected
    shapes are wrapped as ``UserValidationError`` (never raw crash).
    """
    try:
        raw_id = row[0]
        raw_email = row[1]
        raw_hash = row[2]
        return User(
            id=UserId(str(raw_id)),
            email=UserEmail(str(raw_email)),
            password_hash=str(raw_hash),
        )
    except UserValidationError:
        raise
    except (IndexError, TypeError, ValueError, AttributeError) as exc:
        raise UserValidationError(f"Corrupt user row: {exc}") from exc


class PostgresUserRepository(IUserRepository):
    """PostgreSQL adapter for the User aggregate root."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = _require_dsn(dsn)

    def save(self, user: User) -> None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, email, password_hash)"
                " VALUES (%s, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET"
                " email = EXCLUDED.email,"
                " password_hash = EXCLUDED.password_hash",
                (user.id.value, user.email.value, user.password_hash),
            )

    def find_by_email(self, email: UserEmail) -> User | None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash FROM users WHERE email = %s",
                (email.value,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_user(row)
