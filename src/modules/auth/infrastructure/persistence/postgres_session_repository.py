"""ChronoLog PostgresSessionRepository (adapter, psycopg2 only).

Implements the ``ISessionRepository`` port with raw parameterized SQL
(``%s`` placeholders only, no f-strings). Stores ``sha256(token)`` as
``token_hash`` PK, never the raw token. Depends only on the domain
port/entities plus stdlib ``os`` (``DATABASE_URL``), ``datetime`` and
``psycopg2``.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg2  # type: ignore[import-untyped]

from src.modules.auth.domain.entities import AuthSession
from src.modules.auth.domain.exceptions import UserValidationError
from src.modules.auth.domain.repository_interfaces import ISessionRepository
from src.modules.auth.domain.security import hash_token


def _require_dsn(dsn: str | None) -> str:
    value = dsn or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return value


def _row_to_session(row: tuple[Any, ...]) -> AuthSession:
    """Map a ``(token_hash, user_id, expires_at, created_at)`` row.

    The raw token is NOT stored, so the rehydrated session carries an
    empty-string token placeholder — only ``user_id``/expiry matter
    downstream (the middleware already matched the hash). Corrupt rows
    raise domain errors, never raw crash.
    """
    try:
        raw_user_id = row[1]
        raw_expires = row[2]
        raw_created = row[3]
        if not isinstance(raw_expires, datetime) or raw_expires.tzinfo is None:
            raise UserValidationError("Corrupt session expires_at")
        if not isinstance(raw_created, datetime) or raw_created.tzinfo is None:
            raise UserValidationError("Corrupt session created_at")
        return AuthSession(
            token="",
            user_id=str(raw_user_id),
            created_at=raw_created,
            expires_at=raw_expires,
        )
    except UserValidationError:
        raise
    except (IndexError, TypeError, ValueError, AttributeError) as exc:
        raise UserValidationError(f"Corrupt session row: {exc}") from exc


class PostgresSessionRepository(ISessionRepository):
    """PostgreSQL adapter for opaque login sessions."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = _require_dsn(dsn)

    def save(self, session: AuthSession) -> None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, created_at)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (token_hash) DO UPDATE SET"
                " user_id = EXCLUDED.user_id,"
                " expires_at = EXCLUDED.expires_at,"
                " created_at = EXCLUDED.created_at",
                (
                    hash_token(session.token),
                    session.user_id,
                    session.expires_at,
                    session.created_at,
                ),
            )

    def find_by_token_hash(self, token_hash: str) -> AuthSession | None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT token_hash, user_id, expires_at, created_at"
                " FROM sessions WHERE token_hash = %s",
                (token_hash,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        found = _row_to_session(row)
        # Re-attach the hash so callers can match without the raw token.
        # The middleware compares via hash, never via this placeholder.
        object.__setattr__(found, "token", "")
        return found

    def delete_by_token_hash(self, token_hash: str) -> None:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE token_hash = %s",
                (token_hash,),
            )

    def delete_expired(self, now: datetime) -> int:
        with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE expires_at <= %s",
                (now,),
            )
            return cur.rowcount
