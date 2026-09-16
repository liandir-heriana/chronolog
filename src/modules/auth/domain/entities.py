"""ChronoLog User aggregate root + AuthSession (pure domain, stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.modules.auth.domain.exceptions import UserValidationError
from src.modules.auth.domain.security import generate_token
from src.modules.auth.domain.value_objects import UserEmail, UserId


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
    """

    token: str
    user_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def issue(cls, user_id: str) -> AuthSession:
        """Issue a fresh unique-token session for ``user_id``."""
        normalized = user_id.strip()
        if not normalized:
            raise UserValidationError("Session owner user_id must not be empty")
        return cls(token=generate_token(), user_id=normalized)
