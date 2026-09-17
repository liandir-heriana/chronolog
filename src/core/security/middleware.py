"""ChronoLog server-side AuthN/AuthZ middleware contract (TSK-016 D3).

Resolves a bearer token to an ``AuthenticatedUserContext`` via the
``ISessionRepository`` port (hash lookup + expiry check) and guards
cross-tenant access. Every presentation handler MUST call
``authenticate_request`` with the session token from ``gr.State`` and pass
``ctx.user_id`` (never a client-supplied id) into use-cases; cross-user
targets go through ``enforce_user_authorization``.

All auth failures raise the generic ``InvalidCredentialsError`` (unknown,
missing, malformed, expired) so the middleware never becomes an oracle.
``enforce_user_authorization`` raises ``AuthorizationError`` (a
``ValueError``) on mismatch — a programming-error guard, not a user signal.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.auth.domain.exceptions import InvalidCredentialsError
from src.modules.auth.domain.repository_interfaces import ISessionRepository
from src.modules.auth.domain.security import hash_token


class AuthorizationError(ValueError):
    """Raised when an authenticated context targets another user's data."""


@dataclass(frozen=True)
class AuthenticatedUserContext:
    """Proven owner identity for one request (token already validated)."""

    user_id: str
    token_hash: str
    expires_at: datetime


def _extract_token(auth_header: str | None) -> str:
    if auth_header is None:
        raise InvalidCredentialsError()
    raw = auth_header.strip()
    if not raw:
        raise InvalidCredentialsError()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        raise InvalidCredentialsError()
    return raw


def authenticate_request(
    auth_header: str | None,
    sessions: ISessionRepository,
    *,
    now: datetime | None = None,
) -> AuthenticatedUserContext:
    """Validate ``auth_header`` (``Bearer <token>`` or raw token).

    Lookup is by ``sha256(token)``; expired rows (``now >= expires_at``)
    are rejected with the generic error (and best-effort purged).
    """
    moment = now or datetime.now(UTC)
    token = _extract_token(auth_header)
    digest = hash_token(token)
    session = sessions.find_by_token_hash(digest)
    if session is None:
        raise InvalidCredentialsError()
    if session.is_expired(moment):
        with contextlib.suppress(Exception):
            sessions.delete_by_token_hash(digest)
        raise InvalidCredentialsError()
    return AuthenticatedUserContext(
        user_id=session.user_id,
        token_hash=digest,
        expires_at=session.expires_at,
    )


def enforce_user_authorization(
    ctx: AuthenticatedUserContext, target_user_id: str
) -> None:
    """Raise ``AuthorizationError`` unless ``ctx`` owns ``target_user_id``."""
    if ctx.user_id != target_user_id.strip():
        raise AuthorizationError("Forbidden for this user")
