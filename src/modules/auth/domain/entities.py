"""ChronoLog User aggregate root + AuthSession (pure domain, stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.modules.auth.domain.exceptions import UserValidationError
from src.modules.auth.domain.security import generate_token
from src.modules.auth.domain.value_objects import UserEmail, UserId

DEFAULT_SESSION_TTL_HOURS = 12.0


@dataclass
class User:
    """Account aggregate root; ``id`` is the AuthZ `user_id` used downstream.

    Only the password *hash* is stored — plaintext never reaches this entity
    (hashing happens in :mod:`security` before construction).
    """

    id: UserId
    email: UserEmail
    password_hash: str

    def __post_init__(self) -> None:
        if not self.password_hash or not self.password_hash.strip():
            raise UserValidationError("User password_hash must not be empty")


@dataclass(frozen=True)
class AuthSession:
    """Opaque login session: random token bound to one ``user_id``.

    Decision: opaque random token via :mod:`secrets` instead of JWT — zero
    dependencies, server-side revocable in TSK-015 middleware, no claims to
    leak. JWT only if a stateless cross-service need appears.

    TSK-016 (D3): sessions carry ``expires_at`` (default ``created_at`` + 12h)
    and persist server-side (``sessions`` table stores ``sha256(token)``).
    Expired tokens are rejected by the middleware with the generic
    ``InvalidCredentialsError`` — never shipped over HTTP without expiry.
    """

    token: str
    user_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
        + timedelta(hours=DEFAULT_SESSION_TTL_HOURS)
    )

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise UserValidationError("Session datetimes must be timezone-aware")

    @classmethod
    def issue(cls, user_id: str, *, ttl_hours: float = DEFAULT_SESSION_TTL_HOURS) -> AuthSession:
        """Issue a fresh unique-token session for ``user_id`` with a TTL."""
        normalized = user_id.strip()
        if not normalized:
            raise UserValidationError("Session owner user_id must not be empty")
        created = datetime.now(UTC)
        return cls(
            token=generate_token(),
            user_id=normalized,
            created_at=created,
            expires_at=created + timedelta(hours=ttl_hours),
        )

    def is_expired(self, now: datetime) -> bool:
        """Return True when ``now`` is at or past ``expires_at``."""
        if now.tzinfo is None:
            raise UserValidationError("Reference now must be timezone-aware")
        return now >= self.expires_at
